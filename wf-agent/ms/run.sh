docker run --name ow-agent -p 8000:8000 \
-e REDIS_HOST=REDISHOST -e REDIS_PORT -e REDIS_PASS \
-e THIS=http://myaddress:myport/ \
christiansicari/ow-agent
