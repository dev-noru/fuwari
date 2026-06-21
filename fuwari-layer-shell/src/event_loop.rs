use std::sync::mpsc;
use std::thread;
use crate::types::{Command, Event};
use crate::layer;

use smithay_client_toolkit::reexports::calloop::{EventLoop, channel};
use smithay_client_toolkit::reexports::calloop_wayland_source::WaylandSource;

pub fn start() -> (channel::Sender<Command>, mpsc::Receiver<Event>) {
    let (cmd_tx, cmd_rx) = channel::channel::<Command>();
    let (evt_tx, evt_rx) = mpsc::channel();

    thread::spawn(move || {
        let (mut state, event_queue, conn) = layer::new(evt_tx);

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

    (cmd_tx, evt_rx)
}
