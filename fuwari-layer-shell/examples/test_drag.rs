// Throwaway harness: drives the native drag overlay directly, with no Python
// and no FFI, so we test only the Wayland code.
// Run from the crate dir:  cargo run --release --example test_drag

use fuwari_layer_shell::event_loop;
use fuwari_layer_shell::types::{Command, Event};
use std::sync::atomic::Ordering;
use std::time::Duration;

fn main() {
    let (cmd_tx, evt_rx, screen) = event_loop::start();

    // Let the thread bind globals and receive the first output before we drive it.
    std::thread::sleep(Duration::from_millis(300));

    println!(
        ">> screen size from crate: {} x {}",
        screen.width.load(Ordering::Relaxed),
        screen.height.load(Ordering::Relaxed),
    );

    // Pretend a 400x100 window sits at 300,200 and the user grabbed it 200px
    // from its left edge, 10px down -- i.e. in the middle of the toolbar.
    println!(">> Drag ghost is live. Left-click to drop, right-click to cancel.");
    cmd_tx
        .send(Command::StartDrag {
            x: 300,
            y: 200,
            width: 400,
            height: 100,
            grab_x: 200,
            grab_y: 10,
        })
        .expect("failed to send StartDrag");

    loop {
        match evt_rx.recv_timeout(Duration::from_secs(60)) {
            Ok(Event::DragFinished(s)) => {
                println!(">> DragFinished: {}", s);
                break;
            }
            Ok(Event::Error(e)) => {
                println!(">> Error event: {}", e);
                break;
            }
            Ok(_) => {}
            Err(e) => {
                println!(">> Nothing within timeout / channel closed: {:?}", e);
                break;
            }
        }
    }

    cmd_tx.send(Command::Shutdown).ok();
    std::thread::sleep(Duration::from_millis(200));
    println!(">> Done.");
}
