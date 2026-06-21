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
    protocol::wl_seat::WlSeat,
    protocol::wl_shm,
    Connection, QueueHandle,
};
use std::num::NonZeroU32;

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
    // Shared
    seat_state: SeatState,
    pointer: Option<wayland_client::protocol::wl_pointer::WlPointer>,
    pointer_pos: (f64, f64),
    evt_tx: Option<std::sync::mpsc::Sender<crate::types::Event>>,
    regions: Vec<crate::types::Region>,
    shm: Shm,
    width: u32,
    height: u32,
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
    // While region_select is active this drives a refresh-rate-throttled redraw loop.
    fn frame(&mut self, _conn: &Connection, qh: &QueueHandle<Self>, surface: &wayland_client::protocol::wl_surface::WlSurface, _time: u32) {
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
    fn new_output(&mut self, _conn: &Connection, _qh: &QueueHandle<Self>, _output: wayland_client::protocol::wl_output::WlOutput) {}
    fn update_output(&mut self, _conn: &Connection, _qh: &QueueHandle<Self>, _output: wayland_client::protocol::wl_output::WlOutput) {}
    fn output_destroyed(&mut self, _conn: &Connection, _qh: &QueueHandle<Self>, _output: wayland_client::protocol::wl_output::WlOutput) {}
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

        let is_select = self.select_surface.as_ref()
            .map_or(false, |s| s.wl_surface() == layer.wl_surface());

        if is_select {
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
            match event.kind {
                Enter { .. } => {
                    if self.region_select {
                        self.drag_current = event.position;
                    }
                }
                Motion { .. } => {
                    self.pointer_pos = event.position;
                    if self.region_select {
                        // Just record position; the frame-callback loop redraws.
                        self.drag_current = event.position;
                    }
                }
                Press { button, .. } => {
                    if self.region_select {
                        // BTN_LEFT = 272
                        if button == 272 {
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
                    if self.region_select && button == 272 {
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
}

pub fn new(evt_tx: std::sync::mpsc::Sender<crate::types::Event>) -> (OverlayState, wayland_client::EventQueue<OverlayState>, Connection) {
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
        seat_state,
        pointer: None,
        pointer_pos: (0.0, 0.0),
        evt_tx: Some(evt_tx),
        regions: Vec::new(),
        shm,
        width: 1646,
        height: 1097,
        qh: qh.clone(),
        exit: false,
    };
    (state, event_queue, conn)
}
