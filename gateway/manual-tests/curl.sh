# You must the following values in your command line
# GATEWAY_CERT and GATEWAY_KEY are file paths that should match
# the cert files in the same place as CERT_PATH from /conf/gateway-config.yml

# Here are some examples
# export ETH_PRIVATE_KEY='beaaaa2f32280128fa7c18ae77744d5401346ed98c065b1a99e6ed7773850909'
# export GATEWAY_CERT='/home/hummingbot/gateway/certs/client_key.pem'
# export GATEWAY_KEY='/home/hummingbot/gateway/certs/client_cert.pem'

# -k is --insecure, this disables certificate verfication and should only be
# used for local development and testing


# TEST SERVERS

# test that the gateway-api server is running
curl -X GET -k --key $GATEWAY_KEY --cert $GATEWAY_CERT https://localhost:5000/

# test that the gateway-api ethereum server is running
curl -X GET -k --key $GATEWAY_KEY --cert $GATEWAY_CERT https://localhost:5000/eth

curl -X GET -k --key $GATEWAY_KEY --cert $GATEWAY_CERT https://localhost:5000/eth/uniswap


# TEST Ethereum

# get Ethereum balances for your private key
curl -X POST -k --key $GATEWAY_KEY --cert $GATEWAY_CERT -H "Content-Type: application/json" -d "{\"privateKey\":\"$ETH_PRIVATE_KEY\",\"tokenSymbols\":[\"ETH\",\"WETH\",\"DAI\"]}" https://localhost:5000/eth/balances

# get Ethereum allowances for your uniswap on private key
curl -X POST -k --key $GATEWAY_KEY --cert $GATEWAY_CERT -H "Content-Type: application/json" -d "{\"privateKey\":\"$ETH_PRIVATE_KEY\",\"spender\":\"uniswap\",\"tokenSymbols\":[\"DAI\",\"WETH\"]}" https://localhost:5000/eth/allowances

# approve uniswap allowance on your private key
curl -X POST -k --key $GATEWAY_KEY --cert $GATEWAY_CERT -H "Content-Type: application/json" -d "{\"privateKey\":\"$ETH_PRIVATE_KEY\",\"spender\":\"uniswap\",\"token\":\"DAI\"}" https://localhost:5000/eth/approve

# remove uniswap allowance on your private key
curl -X POST -k --key $GATEWAY_KEY --cert $GATEWAY_CERT -H "Content-Type: application/json" -d "{\"privateKey\":\"$ETH_PRIVATE_KEY\",\"spender\":\"uniswap\",\"token\":\"DAI\",\"amount\":\"0\"}" https://localhost:5000/eth/approve

# get the next nonce you should use for your private key
curl -X POST -k --key $GATEWAY_KEY --cert $GATEWAY_CERT -H "Content-Type: application/json" -d "{\"privateKey\":\"$ETH_PRIVATE_KEY\"}" https://localhost:5000/eth/nonce

# call approve with a nonce, if the nonce is incorrect, this should fail
curl -X POST -k --key $GATEWAY_KEY --cert $GATEWAY_CERT -H "Content-Type: application/json" -d "{\"privateKey\":\"$ETH_PRIVATE_KEY\",\"amount\":\"0\",\"spender\":\"approve\",\"token\":\"DAI\",\"nonce\":83}" https://localhost:5000/eth/approve

# poll the status of an ethereum transaction
curl -X POST -k --key $GATEWAY_KEY --cert $GATEWAY_CERT -H "Content-Type: application/json" -d "{\"txHash\":\"0x6d068067a5e5a0f08c6395b31938893d1cdad81f54a54456221ecd8c1941294d\"}" https://localhost:5000/eth/poll