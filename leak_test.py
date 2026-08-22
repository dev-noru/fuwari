import sys, os, cv2
import ocr  # your ocr.py

PAGE = os.sysconf("SC_PAGE_SIZE")
def rss_mb():
    with open("/proc/self/statm") as f:
        return int(f.read().split()[1]) * PAGE / 1024 / 1024

img = cv2.imread(sys.argv[1])
if img is None:
    sys.exit(f"could not read image: {sys.argv[1]}")

pipe = ocr._get_pipeline()   # same arena/mem_pattern patch your app uses
pipe.process(img)            # warm-up

start = rss_mb()
for i in range(1, 401):
    pipe.process(img)        # identical image every time — zero shape variety
    if i % 50 == 0:
        print(f"{i:4d} runs   RSS {rss_mb():7.1f} MB   (+{rss_mb()-start:6.1f})")
