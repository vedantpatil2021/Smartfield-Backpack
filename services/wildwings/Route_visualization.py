import numpy as np
import re
import os
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D


def downsample_data(data, group_size=50):
    """
    downsample data points to an ideal frequency
    """
    downsampled = []
    for i in range(0, len(data), group_size):
        chunk = data[i:i + group_size]

        latitudes = [d['latitude'] for d in chunk if d['latitude'] is not None]
        longitudes = [d['longitude'] for d in chunk if d['longitude'] is not None]
        altitudes = [d['altitude'] for d in chunk if d['altitude'] is not None]

        # means
        mean_lat = np.mean(latitudes) if latitudes else None
        mean_lon = np.mean(longitudes) if longitudes else None
        mean_alt = np.mean(altitudes) if altitudes else None

        # take the first timestamp as the time stap for the set
        downsampled.append({
            'timestamp': chunk[0]['timestamp'],
            'latitude': mean_lat,
            'longitude': mean_lon,
            'altitude': mean_alt
        })
    return downsampled


def parse_drone_data(file_path):
    """
    parse srt data from drone
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    blocks = re.findall(r'<font[^>]*>(.*?)</font>', content, re.DOTALL)

    data = []
    for block in blocks:
        lines = block.strip().splitlines()
        timestamp = lines[1].strip() if len(lines) >= 2 else None

        iso_match = re.search(r'\[iso\s*:\s*(\d+)\]', block)
        shutter_match = re.search(r'\[shutter\s*:\s*([\d/\.]+)\]', block)
        fnum_match = re.search(r'\[fnum\s*:\s*(\d+)\]', block)
        ev_match = re.search(r'\[ev\s*:\s*([\d\.-]+)\]', block)
        ct_match = re.search(r'\[ct\s*:\s*(\d+)\]', block)
        focal_len_match = re.search(r'\[focal_len\s*:\s*(\d+)\]', block)
        lat_match = re.search(r'\[latitude:\s*([\d\.-]+)\]', block)
        lon_match = re.search(r'\[longitude:\s*([\d\.-]+)\]', block)
        alt_match = re.search(r'\[altitude:\s*([\d\.-]+)\]', block)

        iso = int(iso_match.group(1)) if iso_match else None
        shutter = shutter_match.group(1) if shutter_match else None
        fnum = int(fnum_match.group(1)) if fnum_match else None
        ev = float(ev_match.group(1)) if ev_match else None
        ct = int(ct_match.group(1)) if ct_match else None
        focal_len = int(focal_len_match.group(1)) if focal_len_match else None
        latitude = float(lat_match.group(1)) if lat_match else None
        longitude = float(lon_match.group(1)) if lon_match else None
        altitude = float(alt_match.group(1)) if alt_match else None

        data.append({
            'timestamp': timestamp,
            'iso': iso,
            'shutter': shutter,
            'fnum': fnum,
            'ev': ev,
            'ct': ct,
            'focal_len': focal_len,
            'latitude': latitude,
            'longitude': longitude,
            'altitude': altitude
        })
    return data


def plot_drone_path_2d(data, title="drone path"):
    """
    draw 2D drone path according to parsed srt data
    """
    longitudes = [d['longitude'] for d in data if d['longitude'] is not None]
    latitudes = [d['latitude'] for d in data if d['latitude'] is not None]
    timestamps = [d['timestamp'] for d in data if d['timestamp'] is not None]

    plt.figure(figsize=(10, 6))
    plt.plot(longitudes, latitudes, marker='o', linestyle='-', color='blue')
    plt.title(title)
    plt.xlabel('latitude')
    plt.ylabel('longitude')
    plt.grid(True)

    # add timestamp on data point
    # for lon, lat, alt, ts in zip(longitudes, latitudes, altitudes, timestamps):
    #    ax.text(lon, lat, alt, ts, fontsize=8)

    plt.show()

def plot_drone_path_3d(data, title="drone path"):
    """
    draw 3D drone path according to parsed srt data
    """

    longitudes = [d['longitude'] for d in data if d['longitude'] is not None]
    latitudes = [d['latitude'] for d in data if d['latitude'] is not None]
    altitudes = [d['altitude'] for d in data if d['altitude'] is not None]
    timestamps = [d['timestamp'] for d in data if d['timestamp'] is not None]

    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_subplot(111, projection='3d')
    ax.plot(longitudes, latitudes, altitudes, marker='o', linestyle='-', color='blue')
    ax.set_title(title)
    ax.set_xlabel('latitude')
    ax.set_ylabel('longitude')
    ax.set_zlabel('altitude')

    # add timestamp on data point
    # for lon, lat, alt, ts in zip(longitudes, latitudes, altitudes, timestamps):
    #    ax.text(lon, lat, alt, ts, fontsize=8)
    plt.ion()  # interaction
    plt.show()


if __name__ == '__main__':
    # alter the file path to your real file
    current_dir = os.getcwd()
    parent_dir = os.path.dirname(current_dir)
    file_name = 'DJI_0206.SRT'
    file_path = os.path.join(parent_dir, 'DJI_0206.SRT')
    data = parse_drone_data(file_path)
    downsampled_data = downsample_data(data, group_size=50)
    plot_drone_path_2d(downsampled_data, title=file_name)
    plot_drone_path_3d(downsampled_data, title=file_name)