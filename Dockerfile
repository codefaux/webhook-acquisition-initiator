FROM ghcr.io/codefaux/ytdlp-python-base:latest

WORKDIR /app

COPY requirements.txt /app/

RUN pip install --no-cache-dir -r /app/requirements.txt --prefer-binary

COPY aging_queue_manager.py \
     config.py \
     decision_queue_manager.py \
     download_queue_manager.py \
     main.py \
     manual_intervention_manager.py \
     processor.py \
     schema.py \
     server.py \
     telegram_bot.py \
     thread_manager.py \
     util.py \
     ytdlp_interface.py \
     /app/

VOLUME ["/data"]
VOLUME ["/output"]
VOLUME ["/conf"]
# VOLUME ["/temp"]

ENV WAI_CONFIG_FILE=/conf/wai.toml

CMD ["python", "main.py"]
