// Throwaway harness: drives the native region-selection surface directly,
// with no Python and no FFI, so we test only the Wayland code.
// Run from the crate dir:  cargo run --example test_select

use fuwari_layer_shell::event_loop;
use fuwari_layer_shell::types::{Command, Event};
use std::time::Duration;

fn main() {
    // Spawns the Wayland thread; hands back the command sender + event receiver.
    let (cmd_tx, evt_rx, _screen) = event_loop::start();

    // Let the thread bind globals before we drive it.
    std::thread::sleep(Duration::from_millis(150));

    println!(">> Starting region select. Drag a box on screen (or wait 60s).");
    cmd_tx
        .send(Command::StartRegionSelect)
        .expect("failed to send StartRegionSelect");

    loop {
        match evt_rx.recv_timeout(Duration::from_secs(60)) {
            Ok(Event::RegionSelected(s)) => {
                println!(">> RegionSelected: {}", s);
                break;
            }
            Ok(Event::Error(e)) => {
                println!(">> Error event: {}", e);
                break;
            }
            Ok(_) => {} // Ready/Hover/Click — irrelevant here
            Err(e) => {
                println!(">> No region within timeout / channel closed: {:?}", e);
                break;
            }
        }
    }

    cmd_tx.send(Command::Shutdown).ok();
    std::thread::sleep(Duration::from_millis(200));
    println!(">> Done.");
}
