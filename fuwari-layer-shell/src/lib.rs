pub mod types;
pub mod layer;
pub mod event_loop;

use std::ffi::CString;
use std::sync::mpsc;
use types::Command;

pub struct FuwariHandle {
    cmd_tx: smithay_client_toolkit::reexports::calloop::channel::Sender<Command>,
    evt_rx: mpsc::Receiver<types::Event>,
    pending_region: Option<CString>,
    // Capture: Grim instance reused across calls; buffer kept alive for the FFI return.
    grim: Option<grim_rs::Grim>,
    pending_capture: Option<Vec<u8>>,
}

#[unsafe(no_mangle)]
pub extern "C" fn fuwari_start() -> *mut FuwariHandle {
    let (cmd_tx, evt_rx) = event_loop::start();
    let handle = Box::new(FuwariHandle {
    cmd_tx,
    evt_rx,
    pending_region: None,
    grim: None,
    pending_capture: None,});

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

        // Lazily create the Grim instance, then reuse it for every capture.
        if handle.grim.is_none() {
            match grim_rs::Grim::new() {
                Ok(g) => handle.grim = Some(g),
                Err(_) => return std::ptr::null(),
            }
        }
        let grim = handle.grim.as_mut().unwrap();

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
        let handle = &*ptr;
        match handle.evt_rx.try_recv() {
            Ok(types::Event::Click(index)) => index as i32,
            _ => -1,
        }
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
        loop {
            match handle.evt_rx.try_recv() {
                Ok(types::Event::RegionSelected(s)) => {
                    match CString::new(s) {
                        Ok(cs) => {
                            handle.pending_region = Some(cs);
                            return handle.pending_region.as_ref().unwrap().as_ptr();
                        }
                        Err(_) => return std::ptr::null(),
                    }
                }
                Ok(_) => continue, // skip non-region events
                Err(_) => return std::ptr::null(),
            }
        }
    }
}
