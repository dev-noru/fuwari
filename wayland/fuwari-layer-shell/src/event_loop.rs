use std::sync::atomic::{AtomicBool, AtomicI32, AtomicU32};
use std::sync::mpsc;
use std::sync::Arc;
use std::thread;

use crate::layer;
use crate::types::{Command, Event};

use smithay_client_toolkit::reexports::calloop::{channel, EventLoop};
use smithay_client_toolkit::reexports::calloop_wayland_source::WaylandSource;

/// Geometry of the single output Fuwari lives on, in compositor logical pixels.
///
/// Written by the Wayland thread, read by the FFI thread. A Wayland session has
/// N outputs, each with its own size AND its own origin. This describes exactly
/// one of them: the output named via `Command::SetOutputName`. Until that name
/// arrives the crate falls back to whichever output it happened to see last,
/// which is only ever correct on a single-monitor setup.
///
/// `valid` distinguishes "no output resolved yet" from a genuine zero, so a
/// caller can tell a missing answer from a wrong one instead of silently
/// clamping everything to 0x0.
pub struct ScreenSize {
    pub width: AtomicU32,
    pub height: AtomicU32,
    /// Top-left of the output in global compositor space. Non-zero for any
    /// monitor that is not the leftmost/topmost one.
    pub x: AtomicI32,
    pub y: AtomicI32,
    pub valid: AtomicBool,
}

impl ScreenSize {
    fn new() -> Self {
        ScreenSize {
            width: AtomicU32::new(0),
            height: AtomicU32::new(0),
            x: AtomicI32::new(0),
            y: AtomicI32::new(0),
            valid: AtomicBool::new(false),
        }
    }
}

pub fn start() -> (
    channel::Sender<Command>,
    mpsc::Receiver<Event>,
    Arc<ScreenSize>,
) {
    let (cmd_tx, cmd_rx) = channel::channel::<Command>();
    let (evt_tx, evt_rx) = mpsc::channel();

    let screen = Arc::new(ScreenSize::new());
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
                        Command::SetOutputName(name) => state.set_output_name(name),
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
                        Command::SetDebugBoxes { on, rgb } => state.set_debug_boxes(on, rgb),
                        Command::SetHighlight { x, y, width, height, data } =>
                            state.set_highlight(x, y, width, height, data),
                        Command::ClearHighlight => state.clear_highlight(),
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
