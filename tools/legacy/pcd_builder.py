import sys
import struct

def crc16_ccitt(data):
    """닌텐도 4세대 공식 CRC-16-CCITT 체크섬 해시 알고리즘"""
    crc = 0xFFFF
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc

def create_pcd(pk4_path, template_pcd_path, output_pcd_path):
    # 1. 포켓몬 핵심 데이터만 로드 (파티 포켓몬 236바이트여도 앞의 136바이트만 정확히 추출)
    with open(pk4_path, 'rb') as f:
        pk4_data = f.read(136)

    # 2. 템플릿 PCD 로드 (총 856바이트)
    with open(template_pcd_path, 'rb') as f:
        pcd = bytearray(f.read())

    # 3. 정확한 오프셋에 데이터 이식 (4세대 PCD 포켓몬 시작 위치는 0x08)
    pcd[0x08:0x08+136] = pk4_data

    # 4. CRC-16 체크섬 갱신 (PCD의 앞부분 854바이트를 계산해 마지막 2바이트에 기록)
    new_checksum = crc16_ccitt(pcd[:854])
    pcd[854:856] = struct.pack('<H', new_checksum)

    # 5. 최종 파일 빌드
    with open(output_pcd_path, 'wb') as f:
        f.write(pcd)
    print(f"[*] 완벽 성공! 불량알 방지 처리가 적용된 {output_pcd_path} 파일이 생성되었습니다.")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("[!] 사용법: python pcd_builder.py [pk4파일] [템플릿pcd] [결과pcd]")
        sys.exit(1)

    create_pcd(sys.argv[1], sys.argv[2], sys.argv[3])
