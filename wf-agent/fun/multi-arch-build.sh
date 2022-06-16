
#/bin/bash
docker run --rm --privileged \
  multiarch/qemu-user-static \
  --reset -p yes
export DOCKER_CLI_EXPERIMENTAL=enabled
export OPENFAAS_URL="http://pi1:31112"
faas-cli publish -f $1 --platforms linux/arm64,linux/amd64
