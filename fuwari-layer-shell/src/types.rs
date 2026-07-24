#[repr(C)]
#[derive(Clone)]
pub struct Region {
    pub x: i32,
    pub y: i32,
    pub width: i32,
    pub height: i32,
    pub index: usize,
}

pub enum Command {
    Show,
    Hide,
    Resize { width: i32, height: i32 },
    SetRegions(Vec<Region>),
    StartRegionSelect,
    StopRegionSelect,
    StartDrag {
        x: i32,
        y: i32,
        width: i32,
        height: i32,
        grab_x: i32,
        grab_y: i32,
    },
    /// Appearance of the drag ghost. Lengths are in compositor logical pixels,
    /// so the caller scales them before sending.
    SetDragStyle {
        rgb: u32,
        border: i32,
        radius: i32,
        fill_pct: i32,
    },
    StopDrag,
    Shutdown,
}

pub enum Event {
    Ready,
    HoverEnter(usize),
    HoverExit,
    Click(usize),
    RegionSelected(String),
    /// "x,y" on commit, or the literal "cancel" if the user aborted.
    DragFinished(String),
    Error(String),
}
