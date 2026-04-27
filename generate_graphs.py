#!/usr/bin/env python3

import os
import argparse
import pandas as pd
import matplotlib.pyplot as plt
import re
from pathlib import Path
from datetime import datetime

def group_mavlink_columns(columns):
    groups = {}
    
    # Define patterns to categorize columns based on their names
    patterns = {
        'Accelerometer': ['acc'],
        'Gyroscope': ['gyro'],
        'Magnetometer (Compass)': ['mag', 'compass'],
        'Speeds & Rates': ['speed', 'rate', 'vx', 'vy', 'vz'],
        'Attitude (Angles)': ['roll', 'pitch', 'yaw'],
        'Position & Altitude': ['lat', 'lon', 'alt', 'dist'],
        'Vibration & Clipping': ['vibration', 'clip'],
        'Temperature': ['temp'],
        'Power & Battery': ['volt', 'curr', 'vcc', 'vservo'],
        'Errors & Drops': ['error', 'drop', 'fail']
    }
    
    for c in columns:
        clower = c.lower()
        matched = False
        
        # Special handling for angular speeds
        if 'speed' in clower and any(k in clower for k in ['roll', 'pitch', 'yaw']):
            groups.setdefault('Speeds & Rates', []).append(c)
            continue
            
        for g_name, pats in patterns.items():
            if g_name == 'Speeds & Rates': 
                continue
            if any(p in clower for p in pats):
                groups.setdefault(g_name, []).append(c)
                matched = True
                break
                
        if not matched:
            groups.setdefault('Other Metrics', []).append(c)
            
    return groups

def plot_mavlink_csv(csv_path, output_dir):
    try:
        if csv_path.name.startswith('.~lock') or csv_path.stat().st_size == 0:
            return

        df = pd.read_csv(csv_path)
        
        if 'SystemTime_ISO' in df.columns:
            df['Time'] = pd.to_datetime(df['SystemTime_ISO'])
            x_col = 'Time'
            x_label = 'Time'
        elif 'FC_Time_us' in df.columns:
            df['Time'] = df['FC_Time_us'] / 1e6
            x_col = 'Time'
            x_label = 'Flight Controller Time (s)'
        else:
            df['Time'] = df.index
            x_col = 'Time'
            x_label = 'Data Points (Index)'

        numeric_cols = df.select_dtypes(include=['number']).columns
        exclude_cols = ['FC_Time_us', 'SystemTime_ISO', 'Time']
        plot_cols = [c for c in numeric_cols if c not in exclude_cols]
        
        if not plot_cols:
            return
            
        groups = group_mavlink_columns(plot_cols)
        num_groups = len(groups)
        
        if num_groups == 0:
            return
            
        fig, axes = plt.subplots(num_groups, 1, figsize=(12, 3.5 * num_groups), sharex=True)
        if num_groups == 1:
            axes = [axes]
            
        is_datetime = pd.api.types.is_datetime64_any_dtype(df[x_col])
        
        for idx, (group_name, cols) in enumerate(groups.items()):
            ax = axes[idx]
            for col in cols:
                # Downsample if needed
                if len(df[col]) > 10000:
                    ax.plot(df[x_col].iloc[::10], df[col].iloc[::10], label=col, linewidth=0.8)
                else:
                    ax.plot(df[x_col], df[col], label=col, linewidth=1.0)
                    
            ax.set_title(group_name, fontweight='bold')
            ax.grid(True, alpha=0.3)
            ax.legend(loc='center left', bbox_to_anchor=(1.02, 0.5), fontsize='small')
            
            if idx == num_groups - 1:
                ax.set_xlabel(x_label)
                if is_datetime:
                    fig.autofmt_xdate()
        
        fig.suptitle(f"Mavlink Data: {csv_path.name}", fontsize=14, y=0.98 + (0.02 / num_groups))
        plt.tight_layout()
        
        output_file = output_dir / f"{csv_path.stem}.png"
        plt.savefig(output_file, bbox_inches='tight', dpi=100)
        plt.close(fig)
        print(f"  -> Created {output_file}")
    except Exception as e:
        print(f"Error processing {csv_path}: {e}")

def plot_tegrastats(log_path, output_dir):
    times = []
    ram_usage = []
    cpu_temps = []
    gpu_temps = []
    
    try:
        if log_path.stat().st_size == 0:
            return
            
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                time_match = re.search(r'^(\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2})', line)
                if time_match:
                    try:
                        dt = datetime.strptime(time_match.group(1), "%m-%d-%Y %H:%M:%S")
                        times.append(dt)
                    except ValueError:
                        times.append(None)
                else:
                    times.append(None)

                ram_match = re.search(r'RAM (\d+)/', line)
                if ram_match:
                    ram_usage.append(int(ram_match.group(1)))
                else:
                    ram_usage.append(None)
                    
                cpu_match = re.search(r'CPU@([\d\.]+)C', line)
                if cpu_match:
                    cpu_temps.append(float(cpu_match.group(1)))
                else:
                    cpu_temps.append(None)
                    
                gpu_match = re.search(r'GPU@([\d\.]+)C', line)
                if gpu_match:
                    gpu_temps.append(float(gpu_match.group(1)))
                else:
                    gpu_temps.append(None)
                    
        valid_data = [(t, r, c, g) for t, r, c, g in zip(times, ram_usage, cpu_temps, gpu_temps) if r is not None and t is not None]
        
        if not valid_data:
            valid_data = [(i, r, c, g) for i, (t, r, c, g) in enumerate(zip(times, ram_usage, cpu_temps, gpu_temps)) if r is not None]
            if not valid_data:
                return

        times_clean = [d[0] for d in valid_data]
        ram_clean = [d[1] for d in valid_data]
        cpu_clean = [d[2] for d in valid_data]
        gpu_clean = [d[3] for d in valid_data]
            
        fig, ax1 = plt.subplots(figsize=(12, 6))
        
        ax1.plot(times_clean, ram_clean, color='blue', label='RAM Usage (MB)', linewidth=1.5)
        ax1.set_ylabel('RAM Usage (MB)', color='blue', fontweight='bold')
        ax1.tick_params(axis='y', labelcolor='blue')
        ax1.grid(True, alpha=0.3)
        
        if isinstance(times_clean[0], datetime):
            ax1.set_xlabel("Time", fontweight='bold')
            fig.autofmt_xdate()
        else:
            ax1.set_xlabel("Data Points (Index)", fontweight='bold')
        
        ax2 = ax1.twinx()
        if any(t is not None for t in cpu_clean):
            ax2.plot(times_clean, cpu_clean, color='red', label='CPU Temp (°C)', linewidth=1.2, alpha=0.8)
        if any(t is not None for t in gpu_clean):
            ax2.plot(times_clean, gpu_clean, color='orange', label='GPU Temp (°C)', linewidth=1.2, alpha=0.8)
            
        ax2.set_ylabel('Temperature (°C)', color='red', fontweight='bold')
        ax2.tick_params(axis='y', labelcolor='red')
        
        fig.suptitle(f"Jetson Tegrastats: {log_path.name}", fontsize=14)
        
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper left', bbox_to_anchor=(1.05, 1))
        
        plt.tight_layout()
        
        output_file = output_dir / f"{log_path.stem}.png"
        plt.savefig(output_file, bbox_inches='tight', dpi=100)
        plt.close(fig)
        print(f"  -> Created {output_file}")
    except Exception as e:
        print(f"Error processing {log_path}: {e}")

def process_mavlink_folder(folder_path):
    path = Path(folder_path)
    if not path.is_dir():
        print(f"Directory not found: {path}")
        return
        
    print(f"Processing Mavlink directory: {path}")
    output_dir = path / "plots"
    output_dir.mkdir(exist_ok=True)
    
    for file in path.glob("*.csv"):
        plot_mavlink_csv(file, output_dir)

def process_jetson_folder(folder_path):
    path = Path(folder_path)
    if not path.is_dir():
        print(f"Directory not found: {path}")
        return
        
    print(f"Processing Jetson directory: {path}")
    output_dir = path / "plots"
    output_dir.mkdir(exist_ok=True)
    
    for file in path.glob("*.log"):
        if "tegrastats" in file.name:
            plot_tegrastats(file, output_dir)

def main():
    parser = argparse.ArgumentParser(description="Create PNG data graphs from Mavlink CSVs and Jetson logs.")
    parser.add_argument("--mavlink", type=str, help="Path to mavlink folder (e.g., merania/mavlink/1st)")
    parser.add_argument("--jetson", type=str, help="Path to jetson folder (e.g., merania/jetson/1st)")
    
    args = parser.parse_args()
    
    if args.mavlink:
        process_mavlink_folder(args.mavlink)
    elif args.jetson:
        process_jetson_folder(args.jetson)
    else:
        print("No specific flag provided. Processing all directories in 'merania/mavlink' and 'merania/jetson'...")
        base_dir = Path("merania")
        
        mavlink_base = base_dir / "mavlink"
        if mavlink_base.exists() and mavlink_base.is_dir():
            for sub in mavlink_base.iterdir():
                if sub.is_dir() and sub.name != "plots":
                    process_mavlink_folder(sub)
                    
        jetson_base = base_dir / "jetson"
        if jetson_base.exists() and jetson_base.is_dir():
            for sub in jetson_base.iterdir():
                if sub.is_dir() and sub.name != "plots":
                    process_jetson_folder(sub)

if __name__ == "__main__":
    main()
