import sys
import struct

# 1. 닌텐도 4세대 공식 문자표 (일부 영문/기호 예시)
# 이 딕셔너리에 원하는 한글이나 기호의 헥스값을 추가하면 완벽한 커스텀이 가능해.
GEN4_CHAR_MAP = {
    'A': b'\xBB\x00', 'B': b'\xBC\x00', 'C': b'\xBD\x00', 'D': b'\xBE\x00', 'E': b'\xBF\x00',
    'F': b'\xC0\x00', 'G': b'\xC1\x00', 'H': b'\xC2\x00', 'I': b'\xC3\x00', 'J': b'\xC4\x00',
    'K': b'\xC5\x00', 'L': b'\xC6\x00', 'M': b'\xC7\x00', 'N': b'\xC8\x00', 'O': b'\xC9\x00',
    'P': b'\xCA\x00', 'Q': b'\xCB\x00', 'R': b'\xCC\x00', 'S': b'\xCD\x00', 'T': b'\xCE\x00',
    'U': b'\xCF\x00', 'V': b'\xD0\x00', 'W': b'\xD1\x00', 'X': b'\xD2\x00', 'Y': b'\xD3\x00', 'Z': b'\xD4\x00',
    ' ': b'\x00\x00', '!': b'\xAB\x00', '?': b'\xAC\x00', '-': b'\xAE\x00'
}

def string_to_gen4_bytes(text, max_length):
    """문자열을 닌텐도 4세대 헥스 코드로 변환 (종료 바이트 0xFFFF 포함)"""
    result = bytearray()
    for char in text[:max_length]:
        # 매핑표에 없으면 기본값(빈칸) 처리
        result.extend(GEN4_CHAR_MAP.get(char.upper(), b'\x00\x00'))

    # 텍스트가 끝났음을 알리는 닌텐도 특수 마커 (0xFFFF)
    result.extend(b'\xFF\xFF')
    return result

def crc16_ccitt(data):
    """무결성 검증을 위한 닌텐도 공식 CRC-16 계산"""
    crc = 0xFFFF
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc

def build_standalone_pcd(pk4_path, card_id, title_text, output_path):
    # 1. 856바이트의 빈 배열(0x00) 생성
    pcd = bytearray(856)

    # [필수 헤더 세팅]
    pcd[0x00:0x02] = struct.pack('<H', card_id) # 카드 ID (중복방지)
    pcd[0x02] = 0x01 # 배포 아이콘 (1 = 기본 상자)
    pcd[0x04] = 0x01 # 배포 종류 (1 = 포켓몬)

    # 2. PK4 데이터 삽입 (반드시 0x08 오프셋, 136바이트)
    with open(pk4_path, 'rb') as f:
        pk4_data = f.read(136)
    pcd[0x08:0x08+136] = pk4_data

    # 3. 배포 제목 텍스트 삽입 (0x90 오프셋 시작)
    # 제목은 최대 36글자(72바이트)까지 허용
    encoded_title = string_to_gen4_bytes(title_text, 36)
    pcd[0x90:0x90+len(encoded_title)] = encoded_title

    # 4. 전체 파일에 대한 CRC-16 체크섬 계산 후 마지막 2바이트에 서명
    checksum = crc16_ccitt(pcd[:854])
    pcd[854:856] = struct.pack('<H', checksum)

    # 5. 최종 파일 출력
    with open(output_path, 'wb') as f:
        f.write(pcd)
    print(f"[*] 완벽 독립 빌드 성공: {output_path} (카드 ID: {card_id})")

if __name__ == "__main__":
    # 실행 예시: python ultimate_pcd_maker.py ARC.pk4 777 "HELLO ILJAE" ARC_CUSTOM.pcd
    if len(sys.argv) < 5:
        print("사용법: python ultimate_pcd_maker.py [pk4파일] [카드ID숫자] [영문제목] [출력pcd명]")
        sys.exit(1)

    build_standalone_pcd(sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4])
