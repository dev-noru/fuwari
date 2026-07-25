pub mod types;
pub mod layer;
pub mod event_loop;

use std::ffi::CString;
use std::sync::atomic::Ordering;
use std::sync::mpsc;
use std::sync::Arc;
use types::Command;

/// Events drained from the channel but not yet claimed by a poller are kept
/// here. Without this, fuwari_poll_region and fuwari_poll_drag would silently
/// discard each other's events, since they share one receiver.
const STASH_CAP: usize = 64;

pub struct FuwariHandle {
    cmd_tx: smithay_client_toolkit::reexports::calloop::channel::Sender<Command>,
    evt_rx: mpsc::Receiver<types::Event>,
    stash: Vec<types::Event>,
    pending_region: Option<CString>,
    pending_drag: Option<CString>,
    screen: Arc<event_loop::ScreenSize>,
    // Capture: Grim instance reused across calls; buffer kept alive for the FFI return.
    pending_capture: Option<Vec<u8>>,
}

impl FuwariHandle {
    fn drain(&mut self) {
        while let Ok(e) = self.evt_rx.try_recv() {
            if self.stash.len() >= STASH_CAP {
                self.stash.remove(0);
            }
            self.stash.push(e);
        }
    }

    fn take_region(&mut self) -> Option<String> {
        self.drain();
        let idx = self
            .stash
            .iter()
            .position(|e| matches!(e, types::Event::RegionSelected(_)))?;
        match self.stash.remove(idx) {
            types::Event::RegionSelected(s) => Some(s),
            _ => None,
        }
    }

    fn take_drag(&mut self) -> Option<String> {
        self.drain();
        let idx = self
            .stash
            .iter()
            .position(|e| matches!(e, types::Event::DragFinished(_)))?;
        match self.stash.remove(idx) {
            types::Event::DragFinished(s) => Some(s),
            _ => None,
        }
    }

    /// Latest hover state, discarding intermediate transitions: the pointer
    /// may have crossed several regions between polls and only where it came
    /// to rest matters. Returns the index, -1 on exit, -2 if unchanged.
    fn take_hover(&mut self) -> i64 {
        self.drain();
        let mut latest = -2i64;
        self.stash.retain(|e| match e {
            types::Event::HoverEnter(i) => {
                latest = *i as i64;
                false
            }
            types::Event::HoverExit => {
                latest = -1;
                false
            }
            _ => true,
        });
        latest
    }

    fn take_click(&mut self) -> Option<usize> {
        self.drain();
        let idx = self
            .stash
            .iter()
            .position(|e| matches!(e, types::Event::Click(_)))?;
        match self.stash.remove(idx) {
            types::Event::Click(i) => Some(i),
            _ => None,
        }
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn fuwari_start() -> *mut FuwariHandle {
    let (cmd_tx, evt_rx, screen) = event_loop::start();
    let handle = Box::new(FuwariHandle {
        cmd_tx,
        evt_rx,
        stash: Vec::new(),
        pending_region: None,
        pending_drag: None,
        screen,
        pending_capture: None,
    });

    Box::into_raw(handle)
}

/// Capture a screen region. Writes the captured pixel dimensions to `out_w`/`out_h`
/// and returns a pointer to `out_w * out_h * 4` bytes of RGBA data, valid until the
/// next call to `fuwari_capture` or `fuwari_free`. Returns NULL on failure.
///
/// Must always be called from the same thread (holds a Wayland connection).
#[unsafe(no_mangle)]
pub extern "C" fn fuwari_capture(
    ptr: *mut FuwariHandle,
    x: i32,
    y: i32,
    width: i32,
    height: i32,
    out_w: *mut u32,
    out_h: *mut u32,
) -> *const u8 {
    if ptr.is_null() {
        return std::ptr::null();
    }
    unsafe {
        let handle = &mut *ptr;
        handle.pending_capture = None; // release the previous buffer

        // A fresh Grim per capture, deliberately.
        //
        // grim-rs 0.2.0 creates a wl_shm_pool and a wl_buffer for every
        // capture and destroys neither, so a reused instance grows this
        // process and the compositor by a full-screen buffer each time --
        // about 21MB per call at 1440p, on both sides. Grim owns its Wayland
        // connection, and dropping it makes the compositor release everything
        // that connection allocated, which is the only handle on the leak
        // from outside the crate. The cost is one connect and roundtrip per
        // capture, which is immaterial next to OCR at two captures a second.
        let mut grim = match grim_rs::Grim::new() {
            Ok(g) => g,
            Err(_) => return std::ptr::null(),
        };

        let region = grim_rs::Region::new(x, y, width, height);
        let result = match grim.capture_region(region) {
            Ok(r) => r,
            Err(_) => return std::ptr::null(),
        };

        // Read dims before consuming the result.
        if !out_w.is_null() { *out_w = result.width(); }
        if !out_h.is_null() { *out_h = result.height(); }

        // Take ownership of the RGBA bytes and stash them on the handle so the
        // pointer stays valid after we return.
        handle.pending_capture = Some(result.into_data());
        handle.pending_capture.as_ref().unwrap().as_ptr()
    }
}

/// Screen size in compositor logical pixels. Both outputs are set to 0 if no
/// output has been seen yet.
#[unsafe(no_mangle)]
pub extern "C" fn fuwari_screen_size(ptr: *mut FuwariHandle, out_w: *mut u32, out_h: *mut u32) {
    if ptr.is_null() { return; }
    unsafe {
        let handle = &*ptr;
        if !out_w.is_null() { *out_w = handle.screen.width.load(Ordering::Relaxed); }
        if !out_h.is_null() { *out_h = handle.screen.height.load(Ordering::Relaxed); }
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn fuwari_shutdown(ptr: *mut FuwariHandle) {
    if ptr.is_null() { return; }
    unsafe {
        let handle = &*ptr;
        let _ = handle.cmd_tx.send(Command::Shutdown);
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn fuwari_free(ptr: *mut FuwariHandle) {
    if ptr.is_null() { return; }
    unsafe { drop(Box::from_raw(ptr)); }
}

#[unsafe(no_mangle)]
pub extern "C" fn fuwari_show(ptr: *mut FuwariHandle) {
    if ptr.is_null() { return; }
    unsafe {
        let handle = &*ptr;
        handle.cmd_tx.send(Command::Show).ok();
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn fuwari_hide(ptr: *mut FuwariHandle) {
    if ptr.is_null() { return; }
    unsafe {
        let handle = &*ptr;
        handle.cmd_tx.send(Command::Hide).ok();
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn fuwari_poll_event(ptr: *mut FuwariHandle) -> i32 {
    if ptr.is_null() { return -1; }
    unsafe {
        let handle = &mut *ptr;
        match handle.take_click() {
            Some(index) => index as i32,
            None => -1,
        }
    }
}

/// Index of the region under the pointer, -1 when it has left them all, or
/// -2 when nothing has changed since the last call.
#[unsafe(no_mangle)]
pub extern "C" fn fuwari_poll_hover(ptr: *mut FuwariHandle) -> i64 {
    if ptr.is_null() {
        return -2;
    }
    unsafe { (&mut *ptr).take_hover() }
}

/// Paint `data` over the hovered token. `data` is premultiplied ARGB8888,
/// `width * height * 4` bytes, in surface-local logical pixels; it is copied
/// before this returns, so the caller may free it immediately.
#[unsafe(no_mangle)]
pub extern "C" fn fuwari_set_highlight(
    ptr: *mut FuwariHandle,
    x: i32,
    y: i32,
    width: i32,
    height: i32,
    data: *const u8,
    len: usize,
) {
    if ptr.is_null() || data.is_null() || width <= 0 || height <= 0 {
        return;
    }
    if len < (width as usize) * (height as usize) * 4 {
        return;
    }
    unsafe {
        let handle = &*ptr;
        let copied = std::slice::from_raw_parts(data, len).to_vec();
        handle
            .cmd_tx
            .send(crate::types::Command::SetHighlight { x, y, width, height, data: copied })
            .ok();
    }
}

/// Remove the recoloured patch, leaving the glyphs as the game drew them.
#[unsafe(no_mangle)]
pub extern "C" fn fuwari_clear_highlight(ptr: *mut FuwariHandle) {
    if ptr.is_null() {
        return;
    }
    unsafe {
        let handle = &*ptr;
        handle.cmd_tx.send(crate::types::Command::ClearHighlight).ok();
    }
}

/// Outline every region set by `fuwari_set_regions`, so their placement can be
/// checked against the glyphs underneath. Development aid; off by default.
/// `rgb` is 0x00RRGGBB.
#[unsafe(no_mangle)]
pub extern "C" fn fuwari_set_debug_boxes(ptr: *mut FuwariHandle, on: i32, rgb: u32) {
    if ptr.is_null() {
        return;
    }
    unsafe {
        let handle = &*ptr;
        handle
            .cmd_tx
            .send(crate::types::Command::SetDebugBoxes { on: on != 0, rgb })
            .ok();
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn fuwari_set_regions(ptr: *mut FuwariHandle, regions_ptr: *const types::Region, count: usize) {
    if ptr.is_null() || regions_ptr.is_null() { return; }
    unsafe {
        let handle = &*ptr;
        let regions = std::slice::from_raw_parts(regions_ptr, count).to_vec();
        handle.cmd_tx.send(Command::SetRegions(regions)).ok();
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn fuwari_start_region_select(ptr: *mut FuwariHandle) {
    if ptr.is_null() { return; }
    unsafe {
        let handle = &*ptr;
        handle.cmd_tx.send(Command::StartRegionSelect).ok();
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn fuwari_stop_region_select(ptr: *mut FuwariHandle) {
    if ptr.is_null() { return; }
    unsafe {
        let handle = &*ptr;
        handle.cmd_tx.send(Command::StopRegionSelect).ok();
    }
}

/// Returns a pointer to a null-terminated region string ("x,y WxH") if one is
/// ready, or NULL if none is available yet.  The pointer is valid until the next
/// call to fuwari_poll_region or fuwari_free.
#[unsafe(no_mangle)]
pub extern "C" fn fuwari_poll_region(ptr: *mut FuwariHandle) -> *const std::ffi::c_char {
    if ptr.is_null() { return std::ptr::null(); }
    unsafe {
        let handle = &mut *ptr;
        handle.pending_region = None; // release previous string
        match handle.take_region() {
            Some(s) => match CString::new(s) {
                Ok(cs) => {
                    handle.pending_region = Some(cs);
                    handle.pending_region.as_ref().unwrap().as_ptr()
                }
                Err(_) => std::ptr::null(),
            },
            None => std::ptr::null(),
        }
    }
}

/// Show the drag ghost. `x`/`y` are the window's current top-left in screen
/// coordinates; `grab_x`/`grab_y` are the cursor's offset inside the window at
/// the moment the toolbar was pressed. All in compositor logical pixels.
#[unsafe(no_mangle)]
pub extern "C" fn fuwari_start_drag(
    ptr: *mut FuwariHandle,
    x: i32,
    y: i32,
    width: i32,
    height: i32,
    grab_x: i32,
    grab_y: i32,
) {
    if ptr.is_null() { return; }
    unsafe {
        let handle = &*ptr;
        handle.cmd_tx.send(Command::StartDrag { x, y, width, height, grab_x, grab_y }).ok();
    }
}

/// `rgb` is packed 0xRRGGBB. `border` and `radius` are compositor logical
/// pixels; `fill_pct` is the interior opacity, 0-100.
#[unsafe(no_mangle)]
pub extern "C" fn fuwari_set_drag_style(
    ptr: *mut FuwariHandle,
    rgb: u32,
    border: i32,
    radius: i32,
    fill_pct: i32,
) {
    if ptr.is_null() { return; }
    unsafe {
        let handle = &*ptr;
        handle.cmd_tx.send(Command::SetDragStyle { rgb, border, radius, fill_pct }).ok();
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn fuwari_stop_drag(ptr: *mut FuwariHandle) {
    if ptr.is_null() { return; }
    unsafe {
        let handle = &*ptr;
        handle.cmd_tx.send(Command::StopDrag).ok();
    }
}

/// Returns "x,y" once the user drops the window, the literal "cancel" if they
/// aborted, or NULL while the drag is still in progress. The pointer is valid
/// until the next call to fuwari_poll_drag or fuwari_free.
#[unsafe(no_mangle)]
pub extern "C" fn fuwari_poll_drag(ptr: *mut FuwariHandle) -> *const std::ffi::c_char {
    if ptr.is_null() { return std::ptr::null(); }
    unsafe {
        let handle = &mut *ptr;
        handle.pending_drag = None; // release previous string
        match handle.take_drag() {
            Some(s) => match CString::new(s) {
                Ok(cs) => {
                    handle.pending_drag = Some(cs);
                    handle.pending_drag.as_ref().unwrap().as_ptr()
                }
                Err(_) => std::ptr::null(),
            },
            None => std::ptr::null(),
        }
    }
}
