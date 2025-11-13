import sys
from pathlib import Path
from preprocessing import create_staging_directory
from config_generator import generate_myst_config

def build_jupyter_book(source_path, bucket_name, staging_dir="_build_staging"):
    """
    Complete pipeline: stage files, convert syntax, generate config, ready to build
    
    Args:
        source_path: Path to source bucket directory
        bucket_name: Name for the book title
        staging_dir: Where to create staging directory (relative to current working dir)
    
    Returns:
        Path to staging directory ready for building
    """
    source_path = Path(source_path)
    staging_path = Path(staging_dir)
    
    print("=" * 50)
    print("Starting Jupyter Book build preparation")
    print("=" * 50)
    
    # Create staging directory with processed files
    staging_path = create_staging_directory(source_path, staging_path)
    
    # Generate myst.yml in staging directory
    print("\nGenerating myst.yml...")
    generate_myst_config(staging_path, bucket_name)
    
    print("\n" + "=" * 50)
    print("Build preparation complete!")
    print(f"Staging directory: {staging_path}")
    print("\nTo build and preview:")
    print(f"  cd {staging_path}")
    print("  myst start")
    print("=" * 50)
    
    return staging_path

    

if __name__ == "__main__":
    # Check if source path provided as argument
    if len(sys.argv) > 1:
        source_path = sys.argv[1]
    else:
        # Default if no argument
        source_path = "../research_biology_md_local"
    
    # Extract bucket name from path
    bucket_name = Path(source_path).name.replace('_local', '').replace('_gcs', '')
    
    staging_dir = "../_build_staging"
    
    build_jupyter_book(source_path, bucket_name, staging_dir)