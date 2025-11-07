from pathlib import Path

def prettify_folder_name(folder_name): 
    """Convert folder_name to Title Case with spaces"""
    name = folder_name.lstrip('0123456789_')
    name = name.replace('_', ' ')
    return name.title()