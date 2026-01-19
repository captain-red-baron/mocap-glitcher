#!/usr/bin/env python3
"""
Mocap Cutter - Creates reveal effect with random switches and glitch transitions.
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


def create_glitch_segment(original_path: str, modified_path: str, start: float, duration: float, output_file: str):
    """Create a glitch segment that rapidly alternates between both videos with effects."""
    
    # Glitch effect: rapid alternation with RGB shift and noise
    filter_complex = (
        f"[0:v]scale=720:1280,setsar=1,fps=30,rgbashift=rh=-8:bh=8,noise=alls=30:allf=t[v0];"
        f"[1:v]scale=720:1280,setsar=1,fps=30,rgbashift=rh=8:bh=-8,noise=alls=30:allf=t[v1];"
        f"[v0][v1]blend=all_expr='if(eq(mod(floor(T*20),2),0),A,B)'[v]"
    )
    
    subprocess.run([
        "ffmpeg", "-y",
        "-ss", str(start), "-t", str(duration), "-i", original_path,
        "-ss", str(start), "-t", str(duration), "-i", modified_path,
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-profile:v", "high", "-level", "4.0",
        "-g", "30", "-keyint_min", "30",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "1",
        output_file
    ], check=True, capture_output=True)


def create_normal_segment(input_file: str, start: float, duration: float, output_file: str):
    """Create a normal video segment."""
    subprocess.run([
        "ffmpeg", "-y",
        "-ss", str(start), "-i", input_file,
        "-t", str(duration),
        "-vf", "scale=720:1280,setsar=1,fps=30",
        "-c:v", "libx264", "-preset", "fast", "-profile:v", "high", "-level", "4.0",
        "-g", "30", "-keyint_min", "30",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "1",
        output_file
    ], check=True, capture_output=True)


def create_text_card(message: str, duration: float, output_file: str, tmpdir: str):
    """Create a black screen with white text using ImageMagick + ffmpeg."""
    
    # Create text image with ImageMagick
    image_file = os.path.join(tmpdir, "text_card.png")
    subprocess.run([
        "convert",
        "-size", "720x1280",
        "-background", "black",
        "-fill", "white",
        "-font", "Helvetica",
        "-pointsize", "48",
        "-gravity", "center",
        f"caption:{message}",
        image_file
    ], check=True)
    
    # Convert to video with silent audio (match other segments: 30fps, 720x1280)
    subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1", "-framerate", "30", "-t", str(duration), "-i", image_file,
        "-f", "lavfi", "-t", str(duration), "-i", "anullsrc=r=44100:cl=mono",
        "-vf", "scale=720:1280,setsar=1",
        "-r", "30",
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac", "-ar", "44100",
        "-pix_fmt", "yuv420p",
        output_file
    ], check=True)


def create_alternating_video(original_path: str, modified_path: str, output_path: str, message: str = None, seed: int = None):
    """Create video with random switches and glitch transitions."""
    
    if seed is not None:
        random.seed(seed)
    
    duration = get_duration(modified_path)
    halfway = duration / 2
    end_original_start = duration - 2  # Last 2 seconds are original
    
    glitch_duration = 0.3  # Duration of glitch effect
    
    # Generate random segments for the middle part
    segments = []  # List of (start, end, 'original' or 'faceswap', is_glitch)
    
    # First half: faceswap only
    segments.append((0, halfway, 'faceswap', False))
    
    # Middle part: random switches with glitch transitions
    current = halfway
    last_type = 'faceswap'
    
    while current < end_original_start:
        # Random segment duration between 0.5 and 1.5 seconds
        seg_duration = random.uniform(0.5, 1.5)
        seg_end = min(current + seg_duration, end_original_start)
        
        # 70% chance faceswap, 30% chance original
        video_type = 'faceswap' if random.random() < 0.7 else 'original'
        
        # Add glitch transition if switching video type
        if video_type != last_type and current + glitch_duration < seg_end:
            # Add glitch at start of new segment
            segments.append((current, current + glitch_duration, video_type, True))
            current += glitch_duration
        
        # Add normal segment
        if current < seg_end:
            segments.append((current, seg_end, video_type, False))
        
        current = seg_end
        last_type = video_type
    
    # Glitch transition before final original segment
    if end_original_start + glitch_duration < duration:
        segments.append((end_original_start, end_original_start + glitch_duration, 'original', True))
        segments.append((end_original_start + glitch_duration, duration, 'original', False))
    else:
        segments.append((end_original_start, duration, 'original', False))
    
    with tempfile.TemporaryDirectory() as tmpdir:
        part_files = []
        
        for i, (start, end, video_type, is_glitch) in enumerate(segments):
            part_file = os.path.join(tmpdir, f"part_{i:03d}.mp4")
            input_file = modified_path if video_type == 'faceswap' else original_path
            seg_duration = end - start
            
            if is_glitch:
                create_glitch_segment(original_path, modified_path, start, seg_duration, part_file)
            else:
                create_normal_segment(input_file, start, seg_duration, part_file)
            
            part_files.append(part_file)
        
        # Add text card at the end if message provided
        if message:
            text_file = os.path.join(tmpdir, "text_card.mp4")
            create_text_card(message, 2.0, text_file, tmpdir)
            part_files.append(text_file)
        
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
    
    glitch_count = sum(1 for s in segments if s[3])
    print(f"Created video with {len(segments)} segments ({glitch_count} glitch transitions): {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Create reveal effect with random switches and glitch transitions"
    )
    parser.add_argument("original", help="Path to the original video")
    parser.add_argument("modified", help="Path to the modified (face swapped) video")
    parser.add_argument("-o", "--output", default="reveal_output.mp4", help="Output path")
    parser.add_argument("-m", "--message", help="Text message to show at the end (2 seconds)")
    parser.add_argument("-s", "--seed", type=int, help="Random seed for reproducibility")
    
    args = parser.parse_args()
    
    create_alternating_video(args.original, args.modified, args.output, args.message, args.seed)


if __name__ == "__main__":
    main()
