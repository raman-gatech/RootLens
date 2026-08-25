#!/usr/bin/env bash
set -euo pipefail

KIND_VERSION="v0.32.0"
HELM_VERSION="v3.18.6"
TOOLS_DIR="${ROOTLENS_TOOLS_DIR:-.tools}"
BIN_DIR="${TOOLS_DIR}/bin"
DOWNLOAD_DIR="${TOOLS_DIR}/downloads"

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64)
    PLATFORM="darwin-arm64"
    KIND_SHA256="dca67911095a110c2b5c36e26df6cac860c602033e456c0db47be498cdef1ebb"
    HELM_SHA256="48e30d236a1f334c6acb78501be5a851eaa2a267fefeb1131b6484eb2f9f30d7"
    ;;
  Darwin-x86_64)
    PLATFORM="darwin-amd64"
    KIND_SHA256="295ac6d0d634c9819c9907df45e3017d1f13166bd13c3404c45e79f7faa47498"
    HELM_SHA256="80cad0470e38cf25731cdead7c32dfbeb887bc177bd6fa01e31b065722f8f06b"
    ;;
  Linux-aarch64)
    PLATFORM="linux-arm64"
    KIND_SHA256="b92cd615e97585de8ddade28ed5cd7feb4248d717c233eea5b03c37298900f5d"
    HELM_SHA256="5b8e00b6709caab466cbbb0bc29ee09059b8dc9417991dd04b497530e49b1737"
    ;;
  Linux-x86_64)
    PLATFORM="linux-amd64"
    KIND_SHA256="50030de23cf40a18505f20426f6a8506bedf13c6e509244bd1fa9463721b0f54"
    HELM_SHA256="3f43c0aa57243852dd542493a0f54f1396c0bc8ec7296bbb2c01e802010819ce"
    ;;
  *)
    echo "Unsupported platform: $(uname -s)-$(uname -m)" >&2
    exit 1
    ;;
esac

mkdir -p "${BIN_DIR}" "${DOWNLOAD_DIR}"

KIND_DOWNLOAD="${DOWNLOAD_DIR}/kind-${PLATFORM}"
curl -fsSL -o "${KIND_DOWNLOAD}" "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-${PLATFORM}"
printf '%s  %s\n' "${KIND_SHA256}" "${KIND_DOWNLOAD}" | shasum -a 256 -c -
chmod +x "${KIND_DOWNLOAD}"
mv "${KIND_DOWNLOAD}" "${BIN_DIR}/kind"

HELM_ARCHIVE="${DOWNLOAD_DIR}/helm-${HELM_VERSION}-${PLATFORM}.tar.gz"
curl -fsSL -o "${HELM_ARCHIVE}" "https://get.helm.sh/helm-${HELM_VERSION}-${PLATFORM}.tar.gz"
printf '%s  %s\n' "${HELM_SHA256}" "${HELM_ARCHIVE}" | shasum -a 256 -c -
tar -xzf "${HELM_ARCHIVE}" -C "${DOWNLOAD_DIR}"
mv "${DOWNLOAD_DIR}/${PLATFORM}/helm" "${BIN_DIR}/helm"

"${BIN_DIR}/kind" version
"${BIN_DIR}/helm" version --short
