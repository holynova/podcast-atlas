"""Stage image-only decks from the manifest; does not read or render PDFs."""
import json, pathlib, sys
from slide_decks import stage_decks

if __name__ == '__main__':
    print(json.dumps(stage_decks(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])), separators=(',', ':')))
