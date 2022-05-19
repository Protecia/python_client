import settings
import json
import tracemalloc
import linecache


def get_conf(value, key=None):
    try:
        with open(settings.INSTALL_PATH + '/conf/conf.json', 'r') as conf_json:
            data = json.load(conf_json)
            if not key:
                return [c[value] for c in data]
            else:
                value_for_key = [c[value] for c in data if c['key'] == key]
                if value_for_key:
                    return [c[value] for c in data if c['key'] == key][0]
                else:
                    return False
    except (KeyError, FileNotFoundError):
        pass
    try:
        with open(settings.INSTALL_PATH + '/conf/docker.json', 'r') as docker_json:
            data = json.load(docker_json)
            return data[value]
    except (KeyError, FileNotFoundError):
        pass
    return False


def display_top(snapshot, key_type='lineno', limit=10):
    snapshot = snapshot.filter_traces((
        tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
        tracemalloc.Filter(False, "<unknown>"),
    ))
    top_stats = snapshot.statistics(key_type)
    message = f"Top {limit} lines"
    for index, stat in enumerate(top_stats[:limit], 1):
        frame = stat.traceback[0]
        message += f"  {index}: {frame.filename}:{frame.lineno}: {stat.size / 1024} KiB"
        line = linecache.getline(frame.filename, frame.lineno).strip()
        if line:
            message += f'    {line}'
    other = top_stats[limit:]
    if other:
        size = sum(stat.size for stat in other)
        message += f"\n{len(other)} other: {size / 1024} KiB"
    total = sum(stat.size for stat in top_stats)
    message += f"\n Total allocated size: {total / 1024} KiB"
    return message

