"""
메인 실행 스크립트
리드 데이터 전처리 및 보강 파이프라인 실행
"""
import os
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(Path(__file__).parent))

from src.data_processor import DataProcessor
from src.ksic_sic_mapper import KSICSICMapper


def main():
    """메인 실행 함수"""
    # 프로젝트 루트 디렉토리 (이미 위에서 정의됨)
    
    # 입력 파일 경로
    input_csv = project_root / 'csv' / 'FY26 Q4 _CIO Summit_post_01190208__CIO Summit_post_01190208_leads_20250210_20260211.csv'
    
    # 출력 파일 경로
    output_csv = project_root / 'output' / 'enriched_leads_sample.csv'
    
    # 매핑 파일 경로
    mapping_csv = project_root / 'data' / 'ksic_to_sic_mapping.csv'
    
    # 출력 디렉토리 생성
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("리드 데이터 전처리 및 보강 파이프라인")
    print("=" * 60)
    print(f"입력 파일: {input_csv}")
    print(f"출력 파일: {output_csv}")
    print(f"매핑 파일: {mapping_csv}")
    print("=" * 60)
    print()
    
    # 입력 파일 존재 확인
    if not input_csv.exists():
        print(f"오류: 입력 파일을 찾을 수 없습니다: {input_csv}")
        sys.exit(1)
    
    try:
        # 데이터 프로세서 초기화
        processor = DataProcessor()
        
        # CSV 처리
        enriched_df = processor.process_csv(str(input_csv), str(output_csv))
        
        # KSIC→SIC 매핑 적용 (항상 실행 - 매핑 테이블이 없어도 기본 규칙/Gemini 사용)
        print("\nKSIC→SIC 코드 매핑 적용 중...")
        mapper = KSICSICMapper(str(mapping_csv) if mapping_csv.exists() else None)
        
        sic_codes = []
        sic_descriptions = []
        
        for idx, row in enriched_df.iterrows():
            ksic_code = row.get('DART_KSIC_Code', '')
            # KSIC 설명은 현재 DART에서 제공하지 않으므로 None으로 전달
            # 향후 DART API에서 KSIC 설명을 가져올 수 있다면 여기에 추가
            sic_info = mapper.map_ksic_to_sic(ksic_code, ksic_description=None)
            
            if sic_info:
                sic_codes.append(sic_info['SIC_Code'])
                sic_descriptions.append(sic_info.get('SIC_Description', ''))
            else:
                sic_codes.append('')
                sic_descriptions.append('')
        
        enriched_df['SIC_Code'] = sic_codes
        enriched_df['SIC_Description'] = sic_descriptions
        
        # 결과 다시 저장
        enriched_df.to_csv(str(output_csv), index=False, encoding='utf-8-sig')
        
        # 변환 통계 출력
        converted_count = sum(1 for code in sic_codes if code)
        print(f"KSIC→SIC 매핑 완료! (변환된 코드: {converted_count}/{len(sic_codes)}건)")
        
        # 매핑 테이블이 업데이트되었으면 저장
        if not mapper.mapping_df.empty and mapping_csv.exists():
            mapper.mapping_df.to_csv(str(mapping_csv), index=False, encoding='utf-8-sig')
            print(f"매핑 테이블 업데이트: {mapping_csv}")
        
        print("\n" + "=" * 60)
        print("모든 처리가 완료되었습니다!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
