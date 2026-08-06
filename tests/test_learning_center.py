import json
from pathlib import Path
from tradysquid.learning.center import LearningCenter
ROOT=Path(__file__).resolve().parents[1]
def test_exactly_27_lessons_and_search():
    c=LearningCenter(json.loads((ROOT/'config/learning-center.json').read_text())); assert len(c.lessons)==27; assert c.search('Greeks')
