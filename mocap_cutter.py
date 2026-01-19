#!/usr/bin/env python3
"""
Mocap Cutter - Creates reveal effect with random switches.
"""

import argparse
import subprocess
import tempfile
import os
import random


def get_duration(video_path: str) -> float:
    """Get video duration using ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def create_alternating_video(original_path: str, modified_path: str, output_path: str, seed: int = None):
    """Create video with random switches between original and modified."""
    
    if seed is not None:
        random.seed(seed)
    
    duration = get_duration(modified_path)
    halfway = duration / 2
    end_original_start = duration - 2  # Last 2 seconds are original
    
    # Generate random segments for the middle part (halfway to end-2s)
    # 70% faceswap, 30% original
    segments = []  # List of (start, end, 'original' or 'faceswap')
    
    # First half: faceswap only
    segments.append((0, halfway, 'faceswap'))
    
    # Middle part: random switches
    current = halfway
    while current < end_original_start:
        # Random segment duration between 0.3 and 1.5 seconds
        seg_duration = random.uniform(0.3, 1.5)
        seg_end = min(current + seg_duration, end_original_start)
        
        # 70% chance faceswap, 30% chance original
        video_type = 'faceswap' if random.random() < 0.7 else 'original'
        segments.append((current, seg_end, video_type))
        current = seg_end
    
    # Last 2 seconds: original only
    segments.append((end_original_start, duration, 'original'))
    
    with tempfile.TemporaryDirectory() as tmpdir:
        part_files = []
        
        for i, (start, end, video_type) in enumerate(segments):
            part_file = os.path.join(tmpdir, f"part_{i:03d}.mp4")
            input_file = modified_path if video_type == 'faceswap' else original_path
            
            # Extract segment with re-encoding for clean cuts
            subprocess.run([
                "ffmpeg", "-y",
                "-i", input_file,
                "-ss", str(start), "-t", str(end - start),
                "-vf", "scale=720:1280,setsar=1",
                "-c:v", "libx264", "-preset", "fast",
                "-c:a", "aac", "-ar", "44100",
                part_file
            ], check=True, capture_output=True)
            
            part_files.append(part_file)
        
        # Create concat file
        concat_file = os.path.join(tmpdir, "concat.txt")
        with open(concat_file, "w") as f:
            for part_file in part_files:
                f.write(f"file '{part_file}'\n")
        
        # Concatenate all parts
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            output_path
        ], check=True)
    
    print(f"Created video with {len(segments)} segments: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Create reveal effect with random switches"
    )
    parser.add_argument("original", help="Path to the original video")
    parser.add_argument("modified", help="Path to the modified (face swapped) video")
    parser.add_argument("-o", "--output", default="reveal_output.mp4", help="Output path")
    parser.add_argument("-s", "--seed", type=int, help="Random seed for reproducibility")
    
    args = parser.parse_args()
    
    create_alternating_video(args.original, args.modified, args.output, args.seed)


if __name__ == "__main__":
    main()
