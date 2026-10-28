import { encrypt3DS } from '@pretendonetwork/boss-crypto';
let input = ''; for await (const chunk of process.stdin) input += chunk;
const v = JSON.parse(input);
const result = encrypt3DS(Buffer.from(v.key, 'hex'), BigInt(v.serial), [{
  program_id: BigInt(v.titleId), content_datatype: 0x10001,
  ns_data_id: v.nsDataId, version: 1, content: Buffer.from(v.content, 'base64'),
}]);
process.stdout.write(result.toString('base64'));
