use std::sync::atomic::AtomicU32;
use std::sync::mpsc;
use std::sync::Arc;
use std::thread;

use crate::layer;
use crate::types::{Command, Event};

use smithay_client_toolkit::reexports::calloop::{channel, EventLoop};
use smithay_client_toolkit::reexports::calloop_wayland_source::WaylandSource;

/// Written by the Wayland thread (from wl_output logical size, then refined by
/// each layer-surface configure), read by the FFI thread. Zero until the first
/// output arrives.
pub struct ScreenSize {
    pub width: AtomicU32,
    pub height: AtomicU32,
}

pub fn start() -> (
    channel::Sender<Command>,
    mpsc::Receiver<Event>,
    Arc<ScreenSize>,
) {
    let (cmd_tx, cmd_rx) = channel::channel::<Command>();
    let (evt_tx, evt_rx) = mpsc::channel();

    let screen = Arc::new(ScreenSize {
        width: AtomicU32::new(0),
        height: AtomicU32::new(0),
    });
    let screen_for_thread = Arc::clone(&screen);

    thread::spawn(move || {
        let (mut state, event_queue, conn) = layer::new(evt_tx, screen_for_thread);

        let mut event_loop: EventLoop<layer::OverlayState> =
            EventLoop::try_new().expect("failed to create event loop");
        let loop_handle = event_loop.handle();

        // Wayland socket as an event source
        WaylandSource::new(conn, event_queue)
            .insert(loop_handle.clone())
            .expect("failed to insert wayland source");

        // command channel as an event source
        loop_handle
            .insert_source(cmd_rx, |event, _, state| {
                if let channel::Event::Msg(cmd) = event {
                    match cmd {
                        Command::Show => state.show(),
                        Command::Hide => state.hide(),
                        Command::SetRegions(regions) => state.set_regions(regions),
                        Command::StartRegionSelect => state.start_region_select(),
                        Command::StopRegionSelect => state.stop_region_select(),
                        Command::StartDrag {
                            x,
                            y,
                            width,
                            height,
                            grab_x,
                            grab_y,
                        } => state.start_drag(x, y, width, height, grab_x, grab_y),
                        Command::SetDragStyle {
                            rgb,
                            border,
                            radius,
                            fill_pct,
                        } => state.set_drag_style(rgb, border, radius, fill_pct),
                        Command::StopDrag => state.stop_drag(),
                        Command::Shutdown => state.request_exit(),
                        _ => {}
                    }
                }
            })
            .expect("failed to insert command source");

        loop {
            event_loop.dispatch(None, &mut state).ok();
            if state.should_exit() {
                break;
            }
        }
    });

    (cmd_tx, evt_rx, screen)
}
