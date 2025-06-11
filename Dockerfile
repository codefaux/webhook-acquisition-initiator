FROM ghcr.io/codefaux/ytdlp-python-base:latest

# Copy application code
COPY requirements.txt aging_queue_manager.py logger.py main.py matcher.py processor.py queue_manager.py server.py sonarr_api.py util.py ytdlp_interface.py /app/

# Install Python packages
WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt --prefer-binary

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
ENV AGING_RIPENESS_PER_DAY=4
ENV AGING_QUEUE_INTERVAL=5

EXPOSE 8000

# Default command
CMD ["python", "main.py"]
