import sys
import struct
import random

# 1. 닌텐도 4세대 공식 문자표 (영문 대문자, 빈칸)
GEN4_CHAR_MAP = {
    'A': b'\xBB\x00', 'B': b'\xBC\x00', 'C': b'\xBD\x00', 'D': b'\xBE\x00', 'E': b'\xBF\x00',
    'F': b'\xC0\x00', 'G': b'\xC1\x00', 'H': b'\xC2\x00', 'I': b'\xC3\x00', 'J': b'\xC4\x00',
    'K': b'\xC5\x00', 'L': b'\xC6\x00', 'M': b'\xC7\x00', 'N': b'\xC8\x00', 'O': b'\xC9\x00',
    'P': b'\xCA\x00', 'Q': b'\xCB\x00', 'R': b'\xCC\x00', 'S': b'\xCD\x00', 'T': b'\xCE\x00',
    'U': b'\xCF\x00', 'V': b'\xD0\x00', 'W': b'\xD1\x00', 'X': b'\xD2\x00', 'Y': b'\xD3\x00', 'Z': b'\xD4\x00',
    ' ': b'\x00\x00', '!': b'\xAB\x00', '?': b'\xAC\x00', '-': b'\xAE\x00'
}

def string_to_gen4_bytes(text, max_length):
    result = bytearray()
    for char in text[:max_length]:
        result.extend(GEN4_CHAR_MAP.get(char.upper(), b'\x00\x00'))
    result.extend(b'\xFF\xFF') # 텍스트 종료 마커
    return result

def crc16_ccitt(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc

def build_ultimate_myg(pk4_path, card_id, title_text, template_myg_path, output_path):
    # ==========================================
    # STEP 1: 856바이트 순수 소포(PCD) 창조
    # ==========================================
    pcd = bytearray(856)

    pcd[0x00:0x02] = struct.pack('<H', card_id)
    pcd[0x02] = 0x01
    pcd[0x04] = 0x01

    with open(pk4_path, 'rb') as f:
        pcd[0x08:0x08+136] = f.read(136)

    encoded_title = string_to_gen4_bytes(title_text, 36)
    pcd[0x90:0x90+len(encoded_title)] = encoded_title

    checksum = crc16_ccitt(pcd[:854])
    pcd[854:856] = struct.pack('<H', checksum)

    # ==========================================
    # STEP 2: MYG 캡슐화 및 중복 방지 (build_myg 흡수)
    # ==========================================
    # 아무 기존 배포 파일이나 하나 가져와서 80바이트 서버 헤더만 훔쳐옴
    with open(template_myg_path, 'rb') as f:
        myg_header = bytearray(f.read(80))

    # [핵심] 게임이 "이미 받은 소포"라고 착각하지 않게 헤더 앞부분(배포 세션 ID)을 랜덤화
    myg_header[0:4] = random.randbytes(4)

    # ==========================================
    # STEP 3: 최종 936바이트 파일로 융합
    # ==========================================
    with open(output_path, 'wb') as f:
        f.write(myg_header + pcd)

    print(f"[*] 진정한 독립 빌드 성공! 텍스트 삽입 + MYG 캡슐화 완료: {output_path} (936 bytes)")

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("[!] 사용법: python ultimate_myg_maker.py [내pk4파일] [카드ID숫자] [영문제목] [출력명.myg]")
        sys.exit(1)

    # 템플릿으로 쓸 myg 파일의 위치 (기존 파일 아무거나)
    TEMPLATE_MYG = "dlc/CPUK/13dpp.myg"

    build_ultimate_myg(sys.argv[1], int(sys.argv[2]), sys.argv[3], TEMPLATE_MYG, sys.argv[4])
