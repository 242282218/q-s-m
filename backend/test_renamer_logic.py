import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.transfer.renamer import Renamer

def test_renamer():
    renamer = Renamer()
    
    test_cases = [
        # (filename, parent_dir)
        ("11 奥海轮舞@Tacit0924.mp4", "第1季（2020）"),
        ("08 剑似主人形@Tacit0924.mp4", "第1季（2020）"),
        ("01 王令三杀吞天蛤@Tacit0924.mp4", "第1季（2020）"),
        ("第04话@Tacit0924.mp4", "第3季（2022）"),
        ("第04话 地底灵脉 4K@Tacit0924.mp4", "第4季 （2023）"),
        ("01_1080P  @Tacit0924.mp4", "第2季（2021）"),
        ("08.4k.mp4", ""),
        ("07.4k.mp4", ""),
        ("02 4K.mkv", ""),
        ("01 4K.mkv", ""),
        ("1080p.mp4", ""), # edge case
        ("2160p.mp4", "")  # edge case
    ]
    
    for filename, parent in test_cases:
        season, episode = renamer.extract_episode_info(filename)
        parent_season, _ = renamer.extract_episode_info(parent) if parent else (None, None)
        
        final_season = season
        if final_season is None and parent_season is not None:
            final_season = parent_season
            
        print(f"File: {filename:35} | Parent: {parent:15} -> Season: {final_season}, Episode: {episode}")

if __name__ == "__main__":
    test_renamer()
