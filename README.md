# ふわり (Fuwari)
A native Wayland Japanese popup dictionary for Linux, inspired by [rampaa/JL](https://github.com/rampaa/JL).

![Demo](demo.gif)

## Features
- Clipboard-based automatic text capture
- Japanese tokenization via MeCab/fugashi
- Yomitan-format dictionary support
- JPDB frequency rankings
- Anki card mining with AnkiConnect and Local Audio Server support (Anki must be running in the background)
- Follows your system colour scheme via Qt SystemPalette
- Native Wayland support (X11 compatible)

## Dependencies
- Python 3
- PySide6
- fugashi
- unidic
- MeCab with a dictionary (e.g. mecab-git on Arch, mecab + mecab-ipadic on Debian/Ubuntu)
- wl-clipboard

## Installation
To install Fuwari:

**Arch Linux:**
```bash
sudo pacman -S pyside6 python-pip wl-clipboard
yay -S mecab-git
pip install fugashi unidic --break-system-packages
python -m unidic download
```

**Debian/Ubuntu:**
```bash
sudo apt install mecab libmecab-dev mecab-ipadic-utf8
pip install fugashi unidic --break-system-packages
python -m unidic download
```

**Other distros:**
Install MeCab and a MeCab dictionary for your distro, then:
```bash
pip install fugashi unidic --break-system-packages
python -m unidic download
```

**To Run Fuwari:**
```bash
git clone https://github.com/dev-noru/fuwari.git
cd fuwari
python main.py
```

### Dictionary Setup
On first launch, Fuwari will open a window prompting you to import a dictionary if none are found.

To import a dictionary, drop any Yomitan-format `.zip` file into `~/.local/share/fuwari/dictionaries/` and restart Fuwari.

**Recommended dictionaries:**
- **Bilingual:** JMdict from [jmdict-yomitan](https://github.com/themoeway/jmdict-yomitan)
- **Kanji:** KANJIDIC from [jmdict-yomitan](https://github.com/themoeway/jmdict-yomitan)
- **Monolingual & Frequency:** See [MarvNC's Yomitan dictionary collection](https://github.com/MarvNC/yomitan-dictionaries)

### Compositor Setups
Most tiling Wayland compositors will attempt to tile or resize Fuwari's windows. To prevent
this, add the appropriate window rule for your compositor below:

**Hyprland**

Add the below to either your `hyprland.conf` or `windowrules.conf`:
```ini
windowrule = float, class:^(fuwari)$
```

**niri**

Add the below to your `~/.config/niri/config.kdl`:
```kdl
window-rule {
    match app-id="fuwari"
    open-floating true
}
```

**MangoWC**

Add the below to your `~/.config/mango/config.conf`:
```ini
windowrule=isfloating:1,appid:fuwari
```


## Anki Integration
Fuwari supports mining cards directly to Anki via [AnkiConnect](https://ankiweb.net/shared/info/2055492159).

### Requirements
- Anki must be running in the background
- [AnkiConnect](https://ankiweb.net/shared/info/2055492159) addon installed in Anki
- [Local Audio Server](https://ankiweb.net/shared/info/1045800357) addon for audio support (optional)

### Setup
1. Open Fuwari and click the ⚙ gear icon
2. Set your AnkiConnect URL (default: `http://localhost:8765`)
3. Select your deck and note type
4. Click **Load Fields** and map your note fields to Fuwari's data
5. Click **Save**

Once configured, hover over any word and click the **+** button in the definition popup to mine it to Anki.

### Audio (Optional)
For word audio when mining, install the [Local Audio Server](https://ankiweb.net/shared/info/1045800357) addon (`1045800357`) and follow the setup instructions at [yomidevs/local-audio-yomichan](https://github.com/yomidevs/local-audio-yomichan) to download the audio files.

Fuwari connects to the Local Audio Server at `http://localhost:5050` automatically.


## About
Fuwari was made so people can use a Japanese dictionary while playing their favourit VNs (Visual Novels)!
Something like Fuwari already exists on windows which is rampaa's JL, but there is no equivalent for Linux
(trust me, I've tried). So after a long time of contemplation I decided to learn coding just to fix this issue.
And now, here we are! Enjoy your popup dictionary while playing your favourite Visual Novels! Happy Mining ね〜！

Wayland's security model restricts applications from arbitrarily placing windows
above others, which makes building a popup dictionary more challenging than on X11.
Fuwari works around this using Qt window flags and compositor window rules to stay
on top of fullscreen applications.

## Credits
- [rampaa/JL](https://github.com/rampaa/JL) — Inspiration
- [polm/fugashi](https://github.com/polm/fugashi) — MeCab Python wrapper
- [MarvNC/jpdb-freq-list](https://github.com/MarvNC/jpdb-freq-list) — Frequency data
