// record(), the CLI formatting expression, selection, cache and ABI come from the checkout. Only platform
// objects, SDK callbacks, telemetry and timing are replaced for this CPU probe.
extern crate self as tracing;
#[macro_export]
macro_rules! info { ($($arg:tt)*) => {} }
macro_rules! once { ($($arg:tt)*) => {} }
use std::ffi::c_void;
use std::path::PathBuf;
use std::sync::{Mutex, OnceLock};
use std::sync::atomic::{AtomicU32, Ordering::SeqCst};

mod abi;
mod plan;
use plan::Mode;

mod fsr {
    pub fn asked_from_env() -> bool { false }
    pub fn dir_from_env() -> std::path::PathBuf { std::path::PathBuf::new() }
}
struct Sl {
    get_new_frame_token: abi::SlGetNewFrameToken,
    set_constants: abi::SlSetConstants,
    evaluate_feature: abi::SlEvaluateFeature,
}
static SL: OnceLock<Sl> = OnceLock::new();
static PLAN: OnceLock<Plan> = OnceLock::new();
static FUNCTIONS: OnceLock<Functions> = OnceLock::new();

struct EmptyTexture;
impl EmptyTexture {
    // The callbacks do not dereference this opaque resource.
    fn as_raw(&self) -> *mut c_void { std::ptr::from_ref(self).cast_mut().cast() }
}
type Textures = [Option<(EmptyTexture, u32)>; 7];
fn spent(_: usize, _: std::time::Instant) { unreachable!("frame generation is disabled") }

static OPTIONS: AtomicU32 = AtomicU32::new(u32::MAX);
static EVALUATIONS: AtomicU32 = AtomicU32::new(0);
static EXTENTS: Mutex<Vec<(u32, [u32; 2])>> = Mutex::new(Vec::new());
static FRAME: u8 = 0;

static QUERIED: Mutex<Vec<u32>> = Mutex::new(Vec::new());
static PROFILE: OnceLock<String> = OnceLock::new();
const OUTPUT_SIZE: [u32; 2] = [1920,1080];
const SMALL: [u32; 2] = [960,540];
const LARGE: [u32; 2] = [1280,720];

// Every simulated SDK answer is independent of the scene and frame number.
unsafe extern "C" fn optimal(options: *const abi::DlssOptions, settings: *mut abi::DlssOptimalSettings) -> i32 {
    let options = unsafe { &*options };
    if [options.output_width, options.output_height] != OUTPUT_SIZE { return 1; }
    QUERIED.lock().unwrap().push(options.mode);
    let (best, min, max) = match PROFILE.get().map(String::as_str) {
        Some("equal") => (SMALL, SMALL, OUTPUT_SIZE),
        Some("normal") => {
            let best = match options.mode {
                abi::DLSS_DLAA => OUTPUT_SIZE,
                abi::DLSS_MAX_QUALITY => LARGE,
                abi::DLSS_BALANCED => [1113,626],
                abi::DLSS_MAX_PERFORMANCE => SMALL,
                abi::DLSS_ULTRA_PERFORMANCE => [640,360],
                _ => return 1,
            };
            (best, best, best)
        }
        _ => return 1,
    };
    let s = unsafe { &mut *settings };
    [s.optimal_render_width,s.optimal_render_height] = best;
    [s.render_width_min,s.render_height_min] = min;
    [s.render_width_max,s.render_height_max] = max;
    0
}
unsafe extern "C" fn set_options(_: *const abi::ViewportHandle, options: *const abi::DlssOptions) -> i32 {
    let options = unsafe { &*options };
    if [options.output_width, options.output_height] != [1920, 1080] { return 1; }
    OPTIONS.store(options.mode, SeqCst);
    0
}
unsafe extern "C" fn frame(token: *mut *mut abi::FrameToken, _: *const u32) -> i32 {
    unsafe { *token = std::ptr::from_ref(&FRAME).cast_mut().cast() };
    0
}
unsafe extern "C" fn constants(_: *const abi::Constants, _: *const abi::FrameToken, _: *const abi::ViewportHandle) -> i32 { 0 }
unsafe extern "C" fn evaluate(feature: u32, _: *const abi::FrameToken, inputs: *const *const abi::BaseStructure, count: u32, _: *mut c_void) -> i32 {
    if feature != abi::FEATURE_DLSS || count != 5 { return 1; }
    let inputs = unsafe { std::slice::from_raw_parts(inputs, count as usize) };
    if unsafe { (**inputs.first().unwrap()).kind } != abi::VIEWPORT_HANDLE { return 1; }
    let mut extents = EXTENTS.lock().unwrap();
    extents.clear();
    for &header in &inputs[1..] {
        if unsafe { (*header).kind } != abi::RESOURCE_TAG { return 1; }
        let tag = unsafe { &*header.cast::<abi::ResourceTag>() };
        extents.push((tag.kind, [tag.extent.width, tag.extent.height]));
    }
    EVALUATIONS.fetch_add(1, SeqCst);
    0
}

fn dims(size: [u32; 2]) -> String { format!("{}x{}", size[0], size[1]) }

fn main() {
    let mut args = std::env::args().skip(1);
    PROFILE.set(args.next().unwrap()).unwrap();
    let asked = Asked::from_env().unwrap();
    assert!(asked.dlss && asked.series_s && !asked.framegen);
    PLAN.set(Plan { asked, dlss: true, framegen: false }).ok().unwrap();
    SL.set(Sl { get_new_frame_token: frame, set_constants: constants, evaluate_feature: evaluate }).ok().unwrap();
    FUNCTIONS.set(Functions { dlss_optimal: Some(optimal), dlss_set_options: Some(set_options), ..Default::default() }).ok().unwrap();
    let textures: Textures = std::array::from_fn(|i| [COLOUR, DEPTH, MOTION, OUTPUT].contains(&i).then_some((EmptyTexture, 0)));
    for (i, scene) in args.enumerate() {
        let (w, h) = scene.split_once('x').unwrap();
        let render = [w.parse().unwrap(), h.parse().unwrap()];
        let camera = plan::Camera {
            render, output: OUTPUT_SIZE, motion_scale: render.map(|x| x as f32),
            jitter: [0.0; 2], near: 0.1, far: 1000.0, fov_y: 1.0, reset: true, flags: 0,
        };
        let before = QUERIED.lock().unwrap().len();
        let old_evals = EVALUATIONS.load(SeqCst);
        OPTIONS.store(u32::MAX, SeqCst);
        let result = record(std::ptr::null_mut(), &textures, &camera, 1.0, i as u64 + 1);
        let queries = QUERIED.lock().unwrap();
        if i == 0 { assert_eq!(&queries[before..], &plan::MODES); } else { assert_eq!(queries.len(), before); }
        let new_queries = queries.len() - before;
        drop(queries);
        assert_eq!(calls().optimal.len(), plan::MODES.len());
        let evals = EVALUATIONS.load(SeqCst) - old_evals;
        match result {
            Ok(r) => {
                assert_eq!(OPTIONS.load(SeqCst), r.mode);
                assert_eq!(evals, 1);
                assert_eq!(*EXTENTS.lock().unwrap(), vec![
                    (abi::BUFFER_SCALING_INPUT_COLOR, render), (abi::BUFFER_DEPTH, render),
                    (abi::BUFFER_MOTION_VECTORS, render), (abi::BUFFER_SCALING_OUTPUT_COLOR, OUTPUT_SIZE)]);
                let offered = recorded_offer(&r).map(dims).unwrap_or_else(|| "-".into());
                println!("{}\t{}\t{}\t{}\t{}\t{}\t{}", scene, plan::sl_mode_name(r.mode),
                    r.optimal.map(dims).unwrap(), offered, new_queries, evals, check_line(&r, render, OUTPUT_SIZE));
            }
            Err(err) => {
                assert_eq!(OPTIONS.load(SeqCst), u32::MAX);
                assert_eq!(evals, 0);
                assert_eq!(err, format!("no DLSS mode takes a {:?} render for a {:?} output", render, OUTPUT_SIZE));
                println!("{}\tnone\t-\t-\t{}\t0\t{}", scene, new_queries, err);
            }
        }
        assert_eq!(QUERIED.lock().unwrap().len(), before + new_queries);
    }
}
