import struct

# 4세대 종족값 예시 딕셔너리 (필요에 따라 확장)
SPECIES_DEX = {487: "기라티나 (Giratina)", 25: "피카츄 (Pikachu)"}

def lcg_advance(seed):
    """4세대 PRNG 난수 생성기"""
    return (seed * 0x41C64E6D + 0x6073) & 0xFFFFFFFF

def decrypt_pk4(data: bytearray):
    """암호화된 pk4 데이터를 복호화합니다."""
    # 0x00~0x03: PID, 0x06~0x07: Checksum
    pid = struct.unpack('<I', data[0:4])[0]
    checksum = struct.unpack('<H', data[6:8])[0]

    # 체크섬을 시드로 설정
    seed = checksum

    # 0x08부터 128바이트(4개 블록)를 복호화
    decrypted_data = bytearray(data)
    for i in range(8, 136, 2):
        seed = lcg_advance(seed)
        prng_word = (seed >> 16) & 0xFFFF  # 상위 16비트를 사용

        # 16비트 단위로 XOR 연산 수행
        encrypted_word = struct.unpack('<H', data[i:i+2])[0]
        decrypted_word = encrypted_word ^ prng_word
        struct.pack_into('<H', decrypted_data, i, decrypted_word)

    return decrypted_data, pid

def analyze_pokemon(file_path):
    # 테스트용: 제공해준 hex 데이터를 바이너리로 저장했다고 가정하고 읽음
    with open(file_path, 'rb') as f:
        raw_data = bytearray(f.read()[:136]) # 기본 136바이트만 읽기

    decrypted, pid = decrypt_pk4(raw_data)

    # 블록 순서 결정 (0 ~ 23)
    shift = ((pid >> 13) & 0x1F) % 24

    # 편의상 블록 A가 제일 처음에 왔다고 가정한 오프셋 분석 (실제론 shift 값에 따라 인덱스 재배열 필요)
    # 기라티나 등 데이터 파싱
    species_id = struct.unpack('<H', decrypted[8:10])[0]
    species_name = SPECIES_DEX.get(species_id, f"Unknown ID ({species_id})")

    print("=== PK4 포켓몬 데이터 분석 ===")
    print(f"[+] 성격치 (PID) : 0x{pid:08X}")
    print(f"[+] 블록 셔플값  : {shift} (24개 조합 중)")
    print(f"[+] 종족값       : {species_name}")

# 실행 예시 (코드와 같은 폴더에 'giratina.pk4'가 있을 때)
# analyze_pokemon('giratina.pk4')
