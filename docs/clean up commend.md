find tests -type d -name "__pycache__" -exec rm -rf {} +
find tests -type f -name "*.pyc" -delete