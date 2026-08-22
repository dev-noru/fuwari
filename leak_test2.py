import sys, os, cv2, collections
import onnxruntime
import ocr
from meikiocr import MeikiOCR

PAGE = os.sysconf("SC_PAGE_SIZE")
def rss_mb():
    with open("/proc/self/statm") as f:
        return int(f.read().split()[1]) * PAGE / 1024 / 1024

# log every input shape that actually reaches an ONNX Run
seen = collections.Counter()
_run = onnxruntime.InferenceSession.run
def run_logged(self, output_names, input_feed, run_options=None):
    for v in input_feed.values():
        if hasattr(v, "shape"):
            seen[tuple(v.shape)] += 1
    return _run(self, output_names, input_feed, run_options)
onnxruntime.InferenceSession.run = run_logged

img = cv2.imread(sys.argv[1])
if img is None:
    sys.exit("could not read image")

pipe = ocr._get_pipeline()
print("batch patch installed:", getattr(MeikiOCR, "_fuwari_fixed_batch", False))

h, w = img.shape[:2]
pipe.process(img)  # warm-up
start = rss_mb()
for i in range(1, 401):
    crop = img[(i * 13) % (h // 4):, (i * 7) % (w // 4):]  # different crop each time
    pipe.process(crop)
    if i % 100 == 0:
        print(f"{i:4d} runs   RSS {rss_mb():7.1f} MB   (+{rss_mb()-start:6.1f})")

print("\ndistinct ONNX input shapes seen:")
for shape, n in seen.most_common():
    print(f"  {shape}  x{n}")
