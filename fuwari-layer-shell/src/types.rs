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
    Shutdown,
}

pub enum Event {
    Ready,
    HoverEnter(usize),
    HoverExit,
    Click(usize),
    RegionSelected(String),
    Error(String),
}
