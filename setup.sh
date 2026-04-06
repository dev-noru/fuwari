#!/bin/bash
set -e

DATA_DIR="$HOME/.local/share/fuwari"
mkdir -p "$DATA_DIR/jpdb_freq"

echo "Fetching latest jmdict-simplified release..."
JMDICT_TAG=$(curl -s https://api.github.com/repos/scriptin/jmdict-simplified/releases/latest | grep '"tag_name"' | cut -d'"' -f4)

if [ -z "$JMDICT_TAG" ]; then
    echo "Error: Could not fetch latest jmdict-simplified release. Check your internet connection."
    exit 1
fi

echo "Using jmdict-simplified $JMDICT_TAG"

cd /tmp

echo "Downloading dictionary files..."
wget -q --show-progress "https://github.com/scriptin/jmdict-simplified/releases/download/$JMDICT_TAG/jmdict-eng-$JMDICT_TAG.json.tgz"
wget -q --show-progress "https://github.com/scriptin/jmdict-simplified/releases/download/$JMDICT_TAG/jmnedict-all-$JMDICT_TAG.json.tgz"
wget -q --show-progress "https://github.com/scriptin/jmdict-simplified/releases/download/$JMDICT_TAG/kanjidic2-en-$JMDICT_TAG.json.tgz"
wget -q --show-progress "https://github.com/MarvNC/jpdb-freq-list/releases/download/2022-05-09/Freq.JPDB_2022-05-10T03_27_02.930Z.zip"

echo "Extracting..."
tar -xzf "jmdict-eng-$JMDICT_TAG.json.tgz"
tar -xzf "jmnedict-all-$JMDICT_TAG.json.tgz"
tar -xzf "kanjidic2-en-$JMDICT_TAG.json.tgz"
unzip -q "Freq.JPDB_2022-05-10T03_27_02.930Z.zip"

echo "Copying to $DATA_DIR..."
cp jmdict-eng-*.json "$DATA_DIR/jmdict-eng.json"
cp jmnedict-all-*.json "$DATA_DIR/jmnedict-all.json"
cp kanjidic2-en-*.json "$DATA_DIR/kanjidic2-en.json"
cp term_meta_bank_1.json "$DATA_DIR/jpdb_freq/"

echo "All dictionary files installed. Run 'python migrate.py' to build the database."
