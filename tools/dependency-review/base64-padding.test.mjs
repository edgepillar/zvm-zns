// Bounded in-memory regression controls for canonical Base64 padding.
import assert from 'node:assert/strict'
import test from 'node:test'
import {readFileSync} from 'node:fs'
import {createRequire} from 'node:module'
import {createBlock} from '@ethereumjs/block'
import {createCustomCommon, Hardfork, Mainnet} from '@ethereumjs/common'
import {createAccount, createAddressFromString, bytesToHex, hexToBytes} from '@ethereumjs/util'
import {createVM} from '@ethereumjs/vm'
import {decodeFunctionResult, encodeFunctionData} from 'viem'
import solc from 'solc'

const require = createRequire(import.meta.url)
const version = JSON.parse(readFileSync(require.resolve('@openzeppelin/contracts/package.json'), 'utf8')).version
assert.equal(version, process.env.ZNS_TEST_OPENZEPPELIN_VERSION)
assert.ok(['4.9.3', '4.9.6'].includes(version))
assert.match(solc.version(), /^0\.8\.26\+commit\.8a97fa7a\./)

const source = `// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;
import {Base64} from "@openzeppelin/contracts/utils/Base64.sol";
contract PaddingControl {
    function encodeFixture(bytes calldata input, uint8 tail) external pure returns (string memory, bool) {
        require(input.length <= 128);
        uint256 length = input.length;
        bytes memory value = new bytes(length + 32);
        for (uint256 i; i < length; i++) value[i] = input[i];
        for (uint256 i; i < 32; i++) value[length + i] = bytes1(tail);
        bytes32 beforeTail;
        assembly {
            mstore(value, length)
            beforeTail := mload(add(add(value, 32), length))
        }
        string memory encoded = Base64.encode(value);
        bytes32 afterTail;
        assembly { afterTail := mload(add(add(value, 32), length)) }
        return (encoded, beforeTail == afterTail);
    }
}`
const input = {language: 'Solidity', sources: {
  'PaddingControl.sol': {content: source},
  '@openzeppelin/contracts/utils/Base64.sol': {content: readFileSync(require.resolve('@openzeppelin/contracts/utils/Base64.sol'), 'utf8')},
}, settings: {evmVersion: 'paris', optimizer: {enabled: true, runs: 200}, outputSelection: {'*': {'*': ['abi', 'evm.bytecode.object']}}}}
const compiled = JSON.parse(solc.compile(JSON.stringify(input)))
assert.deepEqual((compiled.errors ?? []).filter((error) => error.severity === 'error'), [])
const artifact = compiled.contracts['PaddingControl.sol'].PaddingControl

test('canonical encoding and restoration of the allocated tail across bounded padding cases', async () => {
  const common = createCustomCommon({chainId: 7340469}, Mainnet, {hardfork: Hardfork.Paris})
  const vm = await createVM({common})
  // A synthetic message-frame actor, with no signing key or network transport.
  const caller = createAddressFromString('0x0000000000000000000000000000000000010000')
  await vm.stateManager.putAccount(caller, createAccount({balance: 10n ** 30n}))
  const block = createBlock({header: {timestamp: 1900000000n, number: 100n, gasLimit: 60000000n}}, {common})
  const created = await vm.evm.runCall({caller, data: hexToBytes('0x' + artifact.evm.bytecode.object), gasLimit: 20000000n, block})
  assert.equal(created.execResult.exceptionError, undefined)
  const to = created.createdAddress
  let cases = 0, noncanonical = 0, restored = 0
  for (let length = 0; length <= 96; length++) {
    const bytes = Buffer.from(Array.from({length}, (_, index) => (length * 7 + index * 29) & 255))
    for (const tail of [0, 0x5a, 0xff]) {
      vm.stateManager.originalStorageCache.clear()
      vm.evm.journal.cleanJournal()
      const result = await vm.evm.runCall({caller, to, data: hexToBytes(encodeFunctionData({abi: artifact.abi,
        functionName: 'encodeFixture', args: ['0x' + bytes.toString('hex'), tail]})),
        gasLimit: 20000000n, isStatic: true, skipNonceIncrement: true, block})
      assert.equal(result.execResult.exceptionError, undefined)
      const [encoded, tailRestored] = decodeFunctionResult({abi: artifact.abi, functionName: 'encodeFixture', data: bytesToHex(result.execResult.returnValue)})
      cases++
      assert.equal(tailRestored, true)
      restored++
      if (encoded !== bytes.toString('base64')) {
        noncanonical++
        assert.notEqual(length % 3, 0)
        assert.notEqual(tail, 0)
      }
    }
  }
  assert.equal(cases, 291)
  assert.equal(noncanonical, version === '4.9.3' ? 128 : 0)
  assert.equal(restored, cases)
  console.log('ZNS_BASE64_PADDING_RESULT ' + JSON.stringify({version, cases, noncanonical, tailRestored: restored,
    inMemoryParisMessageFramesOnly: true, signingOrLiveNetworkPerformed: false}))
})
