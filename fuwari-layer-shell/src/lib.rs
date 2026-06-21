pub mod types;
pub mod layer;
pub mod event_loop;

use std::ffi::CString;
use std::sync::mpsc;
use types::Command;

pub struct FuwariHandle {
    cmd_tx: smithay_client_toolkit::reexports::calloop::channel::Sender<Command>,
    evt_rx: mpsc::Receiver<types::Event>,
    // Holds the last RegionSelected string so the C pointer stays valid across the FFI call.
    pending_region: Option<CString>,
}

#[unsafe(no_mangle)]
pub extern "C" fn fuwari_start() -> *mut FuwariHandle {
    let (cmd_tx, evt_rx) = event_loop::start();
    let handle = Box::new(FuwariHandle { cmd_tx, evt_rx, pending_region: None });
    Box::into_raw(handle)
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
