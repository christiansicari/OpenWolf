#/bin/bash
#docker buildx create --use 
#docker buildx build --push -t christiansicari/ow-agent  --platform=linux/amd64,linux/arm64 .
docker buildx build --push -t gabrielemorabito/ow-agent  --platform=linux/amd64,linux/arm64 . --builder mybuilder
