import settings
import json
import tracemalloc
import linecache
import unicodedata
import re

def get_conf(value, key=None, with_filter=None):
    try:
        with open(settings.INSTALL_PATH + '/conf/conf.json', 'r') as conf_json:
            data = json.load(conf_json)
            if not key:
                if not with_filter:
                    return [c[value] for c in data]
                else:
                    return [c[value] for c in data if c[with_filter]]
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


def get_client(*fields):
    try:
        with open(settings.INSTALL_PATH + '/conf/conf.json', 'r') as conf_json:
            data = json.load(conf_json)
            dict_client = {}
            for client in data:
                dict_client[client['key']] = {}
                for f in fields:
                    dict_client[client['key']][f] = client[f]
        return dict_client
    except (KeyError, FileNotFoundError):
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


def slugify(value, allow_unicode=False):
    """
    Taken from https://github.com/django/django/blob/master/django/utils/text.py
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.
    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
    else:
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    return re.sub(r'[-\s]+', '-', value).strip('-_')