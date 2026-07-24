use smithay_client_toolkit::{
    compositor::{CompositorHandler, CompositorState, Region},
    shm::{Shm, ShmHandler, slot::SlotPool},
    output::{OutputHandler, OutputState},
    registry::{ProvidesRegistryState, RegistryState},
    registry_handlers,
    seat::{SeatHandler, SeatState, Capability},
    seat::pointer::{PointerHandler, PointerEvent},
    shell::wlr_layer::{
        Anchor, KeyboardInteractivity, Layer, LayerShell, LayerShellHandler, LayerSurface, LayerSurfaceConfigure,
    },
    shell::WaylandSurface,
    delegate_compositor, delegate_output, delegate_registry, delegate_layer, delegate_shm, delegate_seat, delegate_pointer,
};
use wayland_client::{
    globals::registry_queue_init,
    protocol::wl_output::WlOutput,
    protocol::wl_seat::WlSeat,
    protocol::wl_shm,
    Connection, QueueHandle,
};
use std::num::NonZeroU32;
use std::sync::atomic::Ordering;
use std::sync::Arc;

// BTN_LEFT from linux/input-event-codes.h. Any other button cancels the drag.
const BTN_LEFT: u32 = 272;

pub struct OverlayState {
    registry_state: RegistryState,
    output_state: OutputState,
    compositor_state: CompositorState,
    layer_shell: LayerShell,
    // OCR highlight surface
    layer_surface: Option<LayerSurface>,
    first_configure: bool,
    pool: Option<SlotPool>,
    // Region select surface
    select_surface: Option<LayerSurface>,
    first_select_configure: bool,
    select_pool: Option<SlotPool>,
    region_select: bool,
    drag_start: Option<(f64, f64)>,
    drag_current: (f64, f64),
    // Window drag surface
    //
    // A separate full-screen layer surface that does NOT move. Because it is
    // stationary its surface-local pointer coordinates are screen coordinates,
    // which is the whole reason this exists rather than living in QML: a
    // surface cannot measure a drag of itself without chasing its own tail.
    drag_surface: Option<LayerSurface>,
    first_drag_configure: bool,
    drag_pool: Option<SlotPool>,
    drag_active: bool,
    /// set once the user has committed or cancelled; the ghost freezes and we
    /// wait for the button release before unmapping, so the release cannot leak
    /// through to whatever is underneath.
    drag_done: bool,
    drag_size: (i32, i32),
    drag_pos: (i32, i32),
    /// cursor offset within the window at the moment the toolbar was pressed,
    /// measured by QML in the toolbar's own (stationary) coordinates
    drag_grab: (i32, i32),
    // Ghost appearance, all in compositor logical pixels
    drag_color: (u8, u8, u8),
    drag_border: f32,
    drag_radius: f32,
    drag_fill: f32,
    // Shared
    seat_state: SeatState,
    pointer: Option<wayland_client::protocol::wl_pointer::WlPointer>,
    pointer_pos: (f64, f64),
    evt_tx: Option<std::sync::mpsc::Sender<crate::types::Event>>,
    regions: Vec<crate::types::Region>,
    shm: Shm,
    width: u32,
    height: u32,
    screen: Arc<crate::event_loop::ScreenSize>,
    qh: QueueHandle<OverlayState>,
    exit: bool,
}

delegate_compositor!(OverlayState);
delegate_output!(OverlayState);
delegate_registry!(OverlayState);
delegate_layer!(OverlayState);
delegate_seat!(OverlayState);
delegate_pointer!(OverlayState);

impl ShmHandler for OverlayState {
    fn shm_state(&mut self) -> &mut Shm { &mut self.shm }
}
delegate_shm!(OverlayState);

impl CompositorHandler for OverlayState {
    fn scale_factor_changed(&mut self, _conn: &Connection, _qh: &QueueHandle<Self>, _surface: &wayland_client::protocol::wl_surface::WlSurface, _new_factor: i32) {}
    fn transform_changed(&mut self, _conn: &Connection, _qh: &QueueHandle<Self>, _surface: &wayland_client::protocol::wl_surface::WlSurface, _new_transform: wayland_client::protocol::wl_output::Transform) {}

    // Frame callback: the compositor is ready for the next frame.
    // Drives a refresh-rate-throttled redraw for whichever overlay is live.
    fn frame(&mut self, _conn: &Connection, qh: &QueueHandle<Self>, surface: &wayland_client::protocol::wl_surface::WlSurface, _time: u32) {
        if self.drag_active {
            let is_drag = self.drag_surface.as_ref()
                .map_or(false, |s| s.wl_surface() == surface);
            if is_drag {
                self.draw_drag(qh);
                return;
            }
        }
        if self.region_select {
            let is_select = self.select_surface.as_ref()
                .map_or(false, |s| s.wl_surface() == surface);
            if is_select {
                self.draw_selection(qh);
            }
        }
    }
}

impl OutputHandler for OverlayState {
    fn output_state(&mut self) -> &mut OutputState { &mut self.output_state }
    fn new_output(&mut self, _conn: &Connection, _qh: &QueueHandle<Self>, output: WlOutput) {
        self.adopt_output_size(&output);
    }
    fn update_output(&mut self, _conn: &Connection, _qh: &QueueHandle<Self>, output: WlOutput) {
        self.adopt_output_size(&output);
    }
    fn output_destroyed(&mut self, _conn: &Connection, _qh: &QueueHandle<Self>, _output: WlOutput) {}
}

impl ProvidesRegistryState for OverlayState {
    fn registry(&mut self) -> &mut RegistryState { &mut self.registry_state }
    registry_handlers![OutputState, SeatState];
}

impl LayerShellHandler for OverlayState {
    fn closed(&mut self, _conn: &Connection, _qh: &QueueHandle<Self>, _layer: &LayerSurface) {}

    fn configure(&mut self, _conn: &Connection, qh: &QueueHandle<Self>, layer: &LayerSurface, configure: LayerSurfaceConfigure, _serial: u32) {
        let new_w = NonZeroU32::new(configure.new_size.0).map_or(self.width, NonZeroU32::get);
        let new_h = NonZeroU32::new(configure.new_size.1).map_or(self.height, NonZeroU32::get);
        self.width = new_w;
        self.height = new_h;
        self.screen.width.store(new_w, Ordering::Relaxed);
        self.screen.height.store(new_h, Ordering::Relaxed);

        let is_drag = self.drag_surface.as_ref()
            .map_or(false, |s| s.wl_surface() == layer.wl_surface());
        let is_select = self.select_surface.as_ref()
            .map_or(false, |s| s.wl_surface() == layer.wl_surface());

        if is_drag {
            if self.first_drag_configure {
                self.first_drag_configure = false;
                self.draw_drag(qh);
            }
        } else if is_select {
            if self.first_select_configure {
                self.first_select_configure = false;
                self.draw_selection(qh);
            }
        } else if self.first_configure {
            self.first_configure = false;
            self.draw(qh);
        }
    }
}

impl SeatHandler for OverlayState {
    fn seat_state(&mut self) -> &mut SeatState { &mut self.seat_state }
    fn new_seat(&mut self, _conn: &Connection, _qh: &QueueHandle<Self>, _seat: WlSeat) {}
    fn remove_seat(&mut self, _conn: &Connection, _qh: &QueueHandle<Self>, _seat: WlSeat) {}

    fn new_capability(&mut self, _conn: &Connection, qh: &QueueHandle<Self>, seat: WlSeat, capability: Capability) {
        if capability == Capability::Pointer && self.pointer.is_none() {
            self.pointer = Some(self.seat_state.get_pointer(qh, &seat).expect("failed to create pointer"));
        }
    }

    fn remove_capability(&mut self, _conn: &Connection, _qh: &QueueHandle<Self>, _seat: WlSeat, capability: Capability) {
        if capability == Capability::Pointer && self.pointer.is_some() {
            self.pointer.take().unwrap().release();
        }
    }
}

impl PointerHandler for OverlayState {
    fn pointer_frame(
        &mut self,
        _conn: &Connection,
        _qh: &QueueHandle<Self>,
        _pointer: &wayland_client::protocol::wl_pointer::WlPointer,
        events: &[PointerEvent],
    ) {
        use smithay_client_toolkit::seat::pointer::PointerEventKind::*;
        for event in events {
            // Which of our surfaces is this event for? The drag overlay must
            // only react to its own events, never to the region-select ones.
            let on_drag = self.drag_active
                && self.drag_surface.as_ref()
                    .map_or(false, |s| s.wl_surface() == &event.surface);

            match event.kind {
                Enter { .. } => {
                    if on_drag {
                        // First event we get: the implicit grab from the
                        // toolbar press has ended and focus is finally ours.
                        self.move_ghost(event.position);
                    } else if self.region_select {
                        self.drag_current = event.position;
                    }
                }
                Motion { .. } => {
                    self.pointer_pos = event.position;
                    if on_drag {
                        self.move_ghost(event.position);
                    } else if self.region_select {
                        // Just record position; the frame-callback loop redraws.
                        self.drag_current = event.position;
                    }
                }
                Press { button, .. } => {
                    if on_drag {
                        if self.drag_done {
                            continue;
                        }
                        if button == BTN_LEFT {
                            self.move_ghost(event.position);
                            self.finish_drag(false);
                        } else {
                            self.finish_drag(true);
                        }
                    } else if self.region_select {
                        if button == BTN_LEFT {
                            self.drag_start = Some(event.position);
                            self.drag_current = event.position;
                        }
                    } else {
                        let (x, y) = self.pointer_pos;
                        for region in &self.regions {
                            if x >= region.x as f64
                                && x <= (region.x + region.width) as f64
                                && y >= region.y as f64
                                && y <= (region.y + region.height) as f64
                            {
                                if let Some(tx) = &self.evt_tx {
                                    tx.send(crate::types::Event::Click(region.index)).ok();
                                }
                                break;
                            }
                        }
                    }
                }
                Release { button, .. } => {
                    if on_drag {
                        // Unmap only once the button is up, so the drop click
                        // cannot fall through onto the window underneath.
                        if self.drag_done {
                            self.stop_drag();
                        }
                    } else if self.region_select && button == BTN_LEFT {
                        if let Some((sx, sy)) = self.drag_start.take() {
                            let (ex, ey) = self.drag_current;
                            let x = sx.min(ex) as i32;
                            let y = sy.min(ey) as i32;
                            let w = (sx - ex).abs() as i32;
                            let h = (sy - ey).abs() as i32;
                            if w > 4 && h > 4 {
                                let region_str = format!("{},{} {}x{}", x, y, w, h);
                                if let Some(tx) = &self.evt_tx {
                                    tx.send(crate::types::Event::RegionSelected(region_str)).ok();
                                }
                            }
                        }
                        self.stop_region_select();
                    }
                }
                _ => {}
            }
        }
    }
}

impl OverlayState {
    fn adopt_output_size(&mut self, output: &WlOutput) {
        // Gives us a screen size before any surface has been mapped, so Python
        // can clamp sensibly at startup. Multi-monitor: last output wins.
        if let Some(info) = self.output_state.info(output) {
            if let Some((w, h)) = info.logical_size {
                if w > 0 && h > 0 {
                    self.width = w as u32;
                    self.height = h as u32;
                    self.screen.width.store(w as u32, Ordering::Relaxed);
                    self.screen.height.store(h as u32, Ordering::Relaxed);
                }
            }
        }
    }

    // --- OCR highlight surface methods (unchanged) ---

    pub fn set_regions(&mut self, regions: Vec<crate::types::Region>) {
        self.regions = regions;
        self.update_input_region();
        let qh = self.qh.clone();
        self.draw(&qh);
    }

    pub fn show(&mut self) {
        let qh = self.qh.clone();
        let surface = self.compositor_state.create_surface(&qh);
        let layer_surface = self.layer_shell.create_layer_surface(
            &qh,
            surface,
            Layer::Overlay,
            Some("fuwari_overlay"),
            None,
        );
        layer_surface.set_anchor(Anchor::TOP | Anchor::BOTTOM | Anchor::LEFT | Anchor::RIGHT);
        layer_surface.set_size(self.width, self.height);
        layer_surface.set_exclusive_zone(-1);
        layer_surface.set_keyboard_interactivity(KeyboardInteractivity::None);
        layer_surface.wl_surface().commit();
        self.layer_surface = Some(layer_surface);
        self.first_configure = true;
    }

    pub fn hide(&mut self) {
        self.layer_surface = None;
        self.first_configure = true;
    }

    pub fn request_exit(&mut self) {
        self.exit = true;
    }

    pub fn should_exit(&self) -> bool {
        self.exit
    }

    fn update_input_region(&mut self) {
        let surface = match &self.layer_surface {
            Some(s) => s.wl_surface().clone(),
            None => return,
        };
        let region = match Region::new(&self.compositor_state) {
            Ok(r) => r,
            Err(_) => return,
        };
        for r in &self.regions {
            region.add(r.x, r.y, r.width, r.height);
        }
        surface.set_input_region(Some(region.wl_region()));
        surface.commit();
    }

    fn draw(&mut self, _qh: &QueueHandle<Self>) {
        let width = self.width;
        let height = self.height;
        let stride = width as i32 * 4;

        let pool = self.pool.get_or_insert_with(|| {
            SlotPool::new(width as usize * height as usize * 4, &self.shm).expect("failed to create pool")
        });

        let (buffer, canvas) = pool
            .create_buffer(width as i32, height as i32, stride, wl_shm::Format::Argb8888)
            .expect("failed to create buffer");

        // fully transparent base
        for chunk in canvas.chunks_exact_mut(4) {
            chunk[0] = 0;
            chunk[1] = 0;
            chunk[2] = 0;
            chunk[3] = 0;
        }

        // paint semi-transparent highlight over each region
        for region in &self.regions {
            let x0 = region.x.max(0) as usize;
            let y0 = region.y.max(0) as usize;
            let x1 = (region.x + region.width).min(width as i32) as usize;
            let y1 = (region.y + region.height).min(height as i32) as usize;

            for y in y0..y1 {
                for x in x0..x1 {
                    let offset = y * width as usize * 4 + x * 4;
                    if offset + 3 < canvas.len() {
                        canvas[offset]     = 255; // blue
                        canvas[offset + 1] = 200; // green
                        canvas[offset + 2] = 50;  // red  → amber/gold color
                        canvas[offset + 3] = 80;  // alpha (semi-transparent)
                    }
                }
            }
        }

        if let Some(layer_surface) = &self.layer_surface {
            layer_surface.wl_surface().damage_buffer(0, 0, width as i32, height as i32);
            buffer.attach_to(layer_surface.wl_surface()).expect("buffer attach");
            layer_surface.wl_surface().commit();
        }
    }

    // --- Region select surface methods ---

    pub fn start_region_select(&mut self) {
        if self.region_select {
            return;
        }
        let qh = self.qh.clone();
        let surface = self.compositor_state.create_surface(&qh);
        let layer_surface = self.layer_shell.create_layer_surface(
            &qh,
            surface,
            Layer::Overlay,
            Some("fuwari_select"),
            None,
        );
        layer_surface.set_anchor(Anchor::TOP | Anchor::BOTTOM | Anchor::LEFT | Anchor::RIGHT);
        layer_surface.set_size(self.width, self.height);
        layer_surface.set_exclusive_zone(-1);
        layer_surface.set_keyboard_interactivity(KeyboardInteractivity::None);
        layer_surface.wl_surface().commit();
        self.select_surface = Some(layer_surface);
        self.first_select_configure = true;
        self.region_select = true;
        self.drag_start = None;
        self.drag_current = self.pointer_pos;
    }

    pub fn stop_region_select(&mut self) {
        self.select_surface = None;
        self.select_pool = None;
        self.region_select = false;
        self.drag_start = None;
        self.first_select_configure = true;
    }

    fn draw_selection(&mut self, qh: &QueueHandle<Self>) {
        let width = self.width;
        let height = self.height;
        let stride = width as i32 * 4;

        let select_pool = self.select_pool.get_or_insert_with(|| {
            SlotPool::new(width as usize * height as usize * 4 * 2, &self.shm)
                .expect("failed to create select pool")
        });

        let (buffer, canvas) = match select_pool
            .create_buffer(width as i32, height as i32, stride, wl_shm::Format::Argb8888)
        {
            Ok(r) => r,
            Err(_) => return, // slot still held; the frame loop will retry next frame
        };

        // Dark semi-transparent overlay over the whole screen
        for chunk in canvas.chunks_exact_mut(4) {
            chunk[0] = 0;
            chunk[1] = 0;
            chunk[2] = 0;
            chunk[3] = 128;
        }

        if let Some((sx, sy)) = self.drag_start {
            let (ex, ey) = self.drag_current;
            let x0 = (sx.min(ex) as usize).min(width as usize);
            let y0 = (sy.min(ey) as usize).min(height as usize);
            let x1 = (sx.max(ex) as usize).min(width as usize);
            let y1 = (sy.max(ey) as usize).min(height as usize);

            for y in y0..y1 {
                for x in x0..x1 {
                    let off = y * width as usize * 4 + x * 4;
                    if off + 3 < canvas.len() {
                        canvas[off]     = 0;
                        canvas[off + 1] = 0;
                        canvas[off + 2] = 0;
                        canvas[off + 3] = 0;
                    }
                }
            }

            for t in 0..2usize {
                for x in x0..x1 {
                    let top = (y0 + t).min(height as usize - 1);
                    let off = top * width as usize * 4 + x * 4;
                    if off + 3 < canvas.len() {
                        canvas[off] = 255; canvas[off+1] = 255; canvas[off+2] = 255; canvas[off+3] = 255;
                    }
                    if y1 > t {
                        let bot = y1 - 1 - t;
                        let off = bot * width as usize * 4 + x * 4;
                        if off + 3 < canvas.len() {
                            canvas[off] = 255; canvas[off+1] = 255; canvas[off+2] = 255; canvas[off+3] = 255;
                        }
                    }
                }
                for y in y0..y1 {
                    let left = (x0 + t).min(width as usize - 1);
                    let off = y * width as usize * 4 + left * 4;
                    if off + 3 < canvas.len() {
                        canvas[off] = 255; canvas[off+1] = 255; canvas[off+2] = 255; canvas[off+3] = 255;
                    }
                    if x1 > t {
                        let right = x1 - 1 - t;
                        let off = y * width as usize * 4 + right * 4;
                        if off + 3 < canvas.len() {
                            canvas[off] = 255; canvas[off+1] = 255; canvas[off+2] = 255; canvas[off+3] = 255;
                        }
                    }
                }
            }
        }

        let cx = (self.drag_current.0 as usize).min(width as usize - 1);
        let cy = (self.drag_current.1 as usize).min(height as usize - 1);

        for x in 0..width as usize {
            let off = cy * width as usize * 4 + x * 4;
            if off + 3 < canvas.len() {
                canvas[off] = 255; canvas[off+1] = 255; canvas[off+2] = 255; canvas[off+3] = 200;
            }
        }
        for y in 0..height as usize {
            let off = y * width as usize * 4 + cx * 4;
            if off + 3 < canvas.len() {
                canvas[off] = 255; canvas[off+1] = 255; canvas[off+2] = 255; canvas[off+3] = 200;
            }
        }

        if let Some(select_surface) = &self.select_surface {
            let wl = select_surface.wl_surface();
            // Arm the next frame callback BEFORE committing so the loop continues.
            wl.frame(qh, wl.clone());
            wl.damage_buffer(0, 0, width as i32, height as i32);
            buffer.attach_to(wl).expect("buffer attach");
            wl.commit();
        }
    }

    // --- Window drag surface methods ---

    /// `x`/`y` are the window's current top-left in screen coordinates.
    /// `grab_x`/`grab_y` are where inside the window the user pressed, so the
    /// ghost keeps the same grip on the cursor that a real title bar would.
    pub fn start_drag(&mut self, x: i32, y: i32, width: i32, height: i32, grab_x: i32, grab_y: i32) {
        if self.drag_active {
            return;
        }
        let qh = self.qh.clone();
        let surface = self.compositor_state.create_surface(&qh);
        let layer_surface = self.layer_shell.create_layer_surface(
            &qh,
            surface,
            Layer::Overlay,
            Some("fuwari_drag"),
            None,
        );
        layer_surface.set_anchor(Anchor::TOP | Anchor::BOTTOM | Anchor::LEFT | Anchor::RIGHT);
        layer_surface.set_size(self.width, self.height);
        layer_surface.set_exclusive_zone(-1);
        layer_surface.set_keyboard_interactivity(KeyboardInteractivity::None);
        layer_surface.wl_surface().commit();

        self.drag_surface = Some(layer_surface);
        self.first_drag_configure = true;
        self.drag_active = true;
        self.drag_done = false;
        self.drag_size = (width.max(1), height.max(1));
        self.drag_pos = (x, y);
        self.drag_grab = (grab_x, grab_y);
    }

    /// `rgb` is packed 0xRRGGBB. `border` and `radius` are in compositor
    /// logical pixels; `fill_pct` is the interior opacity, 0-100.
    pub fn set_drag_style(&mut self, rgb: u32, border: i32, radius: i32, fill_pct: i32) {
        self.drag_color = (
            ((rgb >> 16) & 0xFF) as u8,
            ((rgb >> 8) & 0xFF) as u8,
            (rgb & 0xFF) as u8,
        );
        self.drag_border = border.max(1) as f32;
        self.drag_radius = radius.max(0) as f32;
        self.drag_fill = fill_pct.clamp(0, 100) as f32 / 100.0;
    }

    pub fn stop_drag(&mut self) {
        self.drag_surface = None;
        self.drag_pool = None;
        self.drag_active = false;
        self.drag_done = false;
        self.first_drag_configure = true;
    }

    fn move_ghost(&mut self, pos: (f64, f64)) {
        if self.drag_done {
            return;
        }
        let (gx, gy) = self.drag_grab;
        let (w, h) = self.drag_size;
        let max_x = (self.width as i32 - w).max(0);
        let max_y = (self.height as i32 - h).max(0);
        let x = (pos.0 as i32 - gx).clamp(0, max_x);
        let y = (pos.1 as i32 - gy).clamp(0, max_y);
        self.drag_pos = (x, y);
    }

    fn finish_drag(&mut self, cancelled: bool) {
        if self.drag_done {
            return;
        }
        self.drag_done = true;
        let msg = if cancelled {
            "cancel".to_string()
        } else {
            format!("{},{}", self.drag_pos.0, self.drag_pos.1)
        };
        if let Some(tx) = &self.evt_tx {
            tx.send(crate::types::Event::DragFinished(msg)).ok();
        }
    }

    fn draw_drag(&mut self, qh: &QueueHandle<Self>) {
        let width = self.width;
        let height = self.height;
        let stride = width as i32 * 4;

        // Copy everything the drawing needs into locals before borrowing the
        // pool, so `canvas` is the only thing holding a borrow.
        let (gx, gy) = self.drag_pos;
        let (gw, gh) = self.drag_size;
        let (cr, cg, cb) = self.drag_color;
        let border = self.drag_border.max(1.0);
        let fill_a = self.drag_fill;
        // a radius larger than half the shorter side would invert the corners
        let radius = self.drag_radius.clamp(0.0, gw.min(gh) as f32 / 2.0);

        let drag_pool = self.drag_pool.get_or_insert_with(|| {
            SlotPool::new(width as usize * height as usize * 4 * 2, &self.shm)
                .expect("failed to create drag pool")
        });

        let (buffer, canvas) = match drag_pool
            .create_buffer(width as i32, height as i32, stride, wl_shm::Format::Argb8888)
        {
            Ok(r) => r,
            Err(_) => return, // slot still held; retry on the next frame
        };

        // Fully transparent base. Unlike region select we do not dim the
        // screen: the user needs to see where they are dropping the window.
        // fill() is a memset, much cheaper than a per-pixel loop.
        canvas.fill(0);

        // A signed distance field for a rounded rectangle. One number per pixel
        // gives us the corners, the border band and the antialiasing at once,
        // instead of four edge loops that cannot round anything.
        let hw = gw as f32 / 2.0;
        let hh = gh as f32 / 2.0;
        let cx = gx as f32 + hw;
        let cy = gy as f32 + hh;

        // Only touch pixels the ghost can cover, plus a pixel of slack for the
        // antialiased edge.
        let pad = 2;
        let x0 = (gx - pad).clamp(0, width as i32) as usize;
        let y0 = (gy - pad).clamp(0, height as i32) as usize;
        let x1 = (gx + gw + pad).clamp(0, width as i32) as usize;
        let y1 = (gy + gh + pad).clamp(0, height as i32) as usize;

        let row = width as usize * 4;
        for py in y0..y1 {
            for px in x0..x1 {
                let dx = (px as f32 + 0.5 - cx).abs() - (hw - radius);
                let dy = (py as f32 + 0.5 - cy).abs() - (hh - radius);
                let ax = dx.max(0.0);
                let ay = dy.max(0.0);
                let d = (ax * ax + ay * ay).sqrt() + dx.max(dy).min(0.0) - radius;

                // coverage of the shape, and of the shape shrunk by the border
                let outer = (0.5 - d).clamp(0.0, 1.0);
                if outer <= 0.0 {
                    continue;
                }
                let inner = (0.5 - (d + border)).clamp(0.0, 1.0);

                // border is opaque, interior is fill_a; the two are disjoint
                let alpha = (outer - inner) + inner * fill_a;
                if alpha <= 0.0 {
                    continue;
                }

                let off = py * row + px * 4;
                if off + 3 >= canvas.len() {
                    continue;
                }
                // wl_shm ARGB8888 expects premultiplied alpha
                canvas[off]     = (cb as f32 * alpha) as u8;
                canvas[off + 1] = (cg as f32 * alpha) as u8;
                canvas[off + 2] = (cr as f32 * alpha) as u8;
                canvas[off + 3] = (alpha * 255.0) as u8;
            }
        }

        if let Some(drag_surface) = &self.drag_surface {
            let wl = drag_surface.wl_surface();
            // Arm the next frame callback BEFORE committing so the loop continues.
            wl.frame(qh, wl.clone());
            wl.damage_buffer(0, 0, width as i32, height as i32);
            buffer.attach_to(wl).expect("buffer attach");
            wl.commit();
        }
    }
}

pub fn new(
    evt_tx: std::sync::mpsc::Sender<crate::types::Event>,
    screen: Arc<crate::event_loop::ScreenSize>,
) -> (OverlayState, wayland_client::EventQueue<OverlayState>, Connection) {
    let conn = Connection::connect_to_env().unwrap();
    let (globals, event_queue) = registry_queue_init::<OverlayState>(&conn).unwrap();
    let qh = event_queue.handle();
    let compositor_state = CompositorState::bind(&globals, &qh).unwrap();
    let output_state = OutputState::new(&globals, &qh);
    let layer_shell = LayerShell::bind(&globals, &qh).expect("compositor does not support wlr-layer-shell");
    let registry_state = RegistryState::new(&globals);
    let seat_state = SeatState::new(&globals, &qh);
    let shm = Shm::bind(&globals, &qh).expect("wl_shm not available");
    let state = OverlayState {
        registry_state,
        output_state,
        compositor_state,
        layer_shell,
        layer_surface: None,
        first_configure: true,
        pool: None,
        select_surface: None,
        first_select_configure: true,
        select_pool: None,
        region_select: false,
        drag_start: None,
        drag_current: (0.0, 0.0),
        drag_surface: None,
        first_drag_configure: true,
        drag_pool: None,
        drag_active: false,
        drag_done: false,
        drag_size: (0, 0),
        drag_pos: (0, 0),
        drag_grab: (0, 0),
        drag_color: (255, 255, 255),
        drag_border: 2.0,
        drag_radius: 0.0,
        drag_fill: 0.0,
        seat_state,
        pointer: None,
        pointer_pos: (0.0, 0.0),
        evt_tx: Some(evt_tx),
        regions: Vec::new(),
        shm,
        width: 1646,
        height: 1097,
        screen,
        qh: qh.clone(),
        exit: false,
    };
    (state, event_queue, conn)
}
