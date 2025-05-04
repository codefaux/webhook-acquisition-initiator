FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

# Install essential tools
RUN apt-get update && apt-get install -y curl ca-certificates xz-utils && rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip install yt-dlp requests prettytable pathlib pycountry rapidfuzz uvicorn fastapi python-dateutil

# Install ffmpeg static from johnvansickle.com
RUN curl -L -o ffmpeg-release.tar.xz https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz && \
    tar -xvf ffmpeg-release.tar.xz && \
    cd ffmpeg-*-amd64-static && \
    mv ffmpeg ffprobe /usr/local/bin/ && \
    cd .. && \
    rm -rf ffmpeg-release.tar.xz ffmpeg-*-amd64-static

# Set working directory
WORKDIR /app

# Copy application code
COPY main.py matcher.py processor.py queue_manager.py server.py sonarr_api.py ytdlp_interface.py /app/

# Create mount point for data
VOLUME ["/data"]
VOLUME ["/output"]
# VOLUME ["/temp"]

ENV DATA_DIR=/data
ENV SONARR_URL=http://sonarr:8989/
ENV SONARR_API=UNSET
# ENV RADARR_URL=.
# ENV RADARR_API=.
ENV SONARR_IN_PATH=/mnt/sonarr
ENV WAI_OUT_PATH=/output
# ENV WAI_OUT_TEMP=/temp
ENV HONOR_UNMON_EPS=1
ENV HONOR_UNMON_SERIES=1
ENV OVERWRITE_EPS=0

EXPOSE 8000

# Default command
CMD ["python", "main.py"]
