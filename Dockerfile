FROM ghcr.io/codefaux/ytdlp-python-base:latest

# Copy application code
COPY requirements.txt aging_queue_manager.py config.py decision_queue_manager.py download_queue_manager.py main.py manual_intervention_manager.py processor.py schema.py server.py telegram_bot.py thread_manager.py util.py ytdlp_interface.py /app/

# Install Python packages
WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt --prefer-binary

# Create mount point for data
VOLUME ["/data"]
VOLUME ["/output"]
VOLUME ["/conf"]
# VOLUME ["/temp"]

ENV DATA_DIR=/data
ENV SONARR_URL=http://sonarr:8989/
ENV SONARR_API=UNSET
ENV WAI_CONF_FILE=/conf/wai.toml

# Default command
CMD ["python", "main.py"]
