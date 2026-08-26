// Throwaway harness: proves grim-rs can capture a region on your compositor.
// Run from the crate dir:  cargo run --example test_capture

use grim_rs::{Grim, Region};

fn main() -> grim_rs::Result<()> {
    let mut grim = Grim::new()?;

    // x, y, width, height in layout coords (from your test_select run).
    let region = Region::new(244, 266, 818, 560);

    let result = grim.capture_region(region)?;
    println!("Captured {}x{} pixels", result.width(), result.height());

    grim.save_png(result.data(), result.width(), result.height(), "test_capture.png")?;
    println!("Wrote test_capture.png — open it and check the region looks right.");

    Ok(())
}
