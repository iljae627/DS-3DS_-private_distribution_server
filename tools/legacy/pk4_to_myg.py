import os
import random
import struct

def build_myg_from_pk4(pk4_path, template_pcd_path, output_path):
    # 1. 포켓몬 데이터 로드 (4세대 pk4는 보통 136바이트)
    with open(pk4_path, 'rb') as f:
        pk4_data = f.read()

    # 2. 템플릿 PCD 로드 (856바이트)
    with open(template_pcd_path, 'rb') as f:
        pcd_data = bytearray(f.read())

    # 3. PCD 내부에 포켓몬 데이터 삽입 (오프셋 0x58 지점 등 템플릿 구조에 따라 다름)
    # 주의: 이 오프셋은 템플릿.pcd 파일의 구조에 따라 다를 수 있음
    pcd_data[0x58:0x58+len(pk4_data)] = pk4_data

    # 4. MYG 헤더 생성 및 배포 ID 랜덤화 (중복 수령 방지)
    # 기존 13dpp.myg의 헤더(80바이트)를 가져옴
    template_myg_path = "dlc/CPUK/13dpp.myg"
    with open(template_myg_path, 'rb') as f:
        header = bytearray(f.read(80))

    # 헤더의 첫 4바이트(배포 고유 ID)를 랜덤하게 덮어씀
    header[0:4] = random.randbytes(4)

    # 5. 최종 파일 빌드
    with open(output_path, 'wb') as f:
        f.write(header + pcd_data)

    print(f"[*] 성공! {output_path} 생성 완료 (중복 방지 ID 적용)")

# 사용법
build_myg_from_pk4("my_pokemon.pk4", "template.pcd", "iljae_custom.myg")
