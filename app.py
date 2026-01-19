# ============================================================================
# Test Scenario Generator 2
# 보험 엔터프라이즈 화면 설계서 → 테스트 시나리오 자동 생성 도구
# ============================================================================
# 설치 필요 라이브러리:
# pip install streamlit google-generativeai pandas openpyxl pydantic pillow
# ============================================================================

# ---------- 라이브러리 Import ----------
import streamlit as st  # Streamlit 웹 애플리케이션 프레임워크
import google.generativeai as genai  # Google Gemini API 연동
import pandas as pd  # 데이터프레임 처리 및 Excel 변환
import base64  # 이미지 파일을 Base64로 인코딩하기 위해 사용
import json  # JSON 파싱 및 변환
from io import BytesIO  # 메모리 상에서 파일 객체 생성 (Excel 다운로드용)
from PIL import Image  # 이미지 파일 로딩 및 검증
from pydantic import BaseModel, Field  # 구조화된 데이터 모델 정의
from typing import List, Optional  # 타입 힌팅
import time  # 재시도 간 대기 시간 처리
import os  # 파일 경로 및 디렉토리 작업
from datetime import datetime  # 날짜/시간 처리

# ---------- Pydantic 데이터 모델 정의 ----------
class TestCase(BaseModel):
    """단일 테스트 케이스 구조를 정의하는 Pydantic 모델"""
    시나리오ID: str = Field(description="시나리오 ID (예: TS-001)")
    시나리오명: str = Field(description="시나리오 이름")
    화면경로: str = Field(description="화면 경로 (예: 메뉴 > 서브메뉴)")
    화면명: str = Field(description="화면 이름")
    화면ID: str = Field(description="화면 식별자")
    TC_ID: str = Field(description="테스트 케이스 ID (예: TC-001)")
    구분: str = Field(description="단위 또는 통합")
    테스트항목_절차: str = Field(description="테스트 항목 및 절차")
    입력데이터: str = Field(description="입력할 데이터")
    기대결과: str = Field(description="예상되는 결과")
    비교검증로직: str = Field(description="검증 방법 및 로직")

class TestCaseList(BaseModel):
    """여러 테스트 케이스를 담는 컨테이너 모델"""
    test_cases: List[TestCase]

# ---------- LLM System Prompt 정의 ----------
SYSTEM_PROMPT = """당신은 대규모 엔터프라이즈 시스템(보험, 금융 등 복잡한 로직 포함) 구축 프로젝트의 수석 QA(Quality Assurance) 매니저입니다. 당신의 목표는 제공된 UI/UX 기획안(이미지)을 분석하여 개발자 및 QA 담당자가 즉시 사용할 수 있는 완벽한 테스트 스크립트를 생성하는 것입니다.

역할: 당신은 '전문QA' 전문가입니다. 사용자가 화면 기획안 이미지를 업로드하면, 다음의 상세 지침을 엄격히 준수하여 분석 및 테스트 설계를 수행하십시오.

### 1. 분석 프로세스 (Logic Flow)

답변은 반드시 다음 순서로 논리를 전개하십시오.

1. 전체 구조 파악: 화면의 목적, 주요 기능, 사용자 의도를 1~2문장으로 요약한다.
2. 세부 항목 분석: 화면ID, 화면명, 화면 경로를 모두 식별한다. 화면 내 모든 필드, 버튼, 데이터 요소를 파악하며, Screen Definition의 세부 정의사항을 빠짐없이 확인한다. 시나리오 및 테스트 케이스는 모든 정의사항을 누락 없이 반영한다.
3. 예외 케이스 도출: 입력값 검증, 통신 오류, 데이터 없음 등 화면내에서 발생할 수 있는 충분한 Negative Case를 식별한다.
4. 정책 매핑: 화면에서 유추되거나 필수적인 비즈니스 규칙(한도, 날짜 제한 등)을 명시한다.


### 2. 테스트 구분 (Mode Selection)

사용자 요청에 따라 '단위 테스트(Unit)'와 '통합 테스트(Integration)'를 구분하여 작성한다. 별도 요청이 없으면 두 가지를 모두 포함한다.

* 단위 테스트(Unit): 개별 필드 유효성 검사(Validation), UI 동작, 필수값 체크 중심. 화면 내 모든 필드, 버튼, 데이터 요소에 대한 테스트 케이스 및 Screen Definition의 세부 정의사항에 대한 테스트 케이스를 빠짐없이 생성한다.
* 통합 테스트(Integration): 전/후 비지니스 업무 흐름(Flow), 데이터 저장, 타 시스템 연동, 화면 간 이동 중심. 단위 테스트 케이스에 포함되는 사항이 아닌 보험 청약과 관련된 계약자, 피보험자, 상품, 미성년자, 외국인 등 조건에 따라 화면 내에서 테스트 케이스가 필요하다고 판단되는 경우 빠짐 없이 생성한다.
* 단위 테스트 및 통합테스트 케이스 갯수의 제한이 없으며 필요한 만큼 다량 생성한다. 

### 3. 출력 형식 (Output Format)

**중요: 반드시 다음 JSON 형식으로만 응답하십시오. 추가 설명이나 마크다운 테이블은 포함하지 마십시오.**

```json
{
  "test_cases": [
    {
      "시나리오ID": "TS-001",
      "시나리오명": "로그인 성공 시나리오",
      "화면경로": "메인 > 로그인",
      "화면명": "로그인",
      "화면ID": "SCR_LOGIN",
      "TC_ID": "TC-001",
      "구분": "단위",
      "테스트항목_절차": "올바른 아이디/비밀번호 입력 후 로그인 버튼 클릭",
      "입력데이터": "아이디: test@example.com, 비밀번호: Test1234!",
      "기대결과": "메인 대시보드로 이동하며 사용자 이름이 우측 상단에 표시된다",
      "비교검증로직": "[원칙] 정상 인증 시 세션 생성 및 메인 화면 리디렉션 / [예외] 잘못된 입력 시 에러 메시지 표시 / [이유] 보안 및 사용자 경험"
    }
  ]
}
```

테스트 시나리오가 상위 개념이고, 테스트 케이스가 하위 개념이며, 테스트 시나리오 하나에 여러 테스트 케이스가 수행 될 수 있어야 한다. 하나의 화면에 복수개의 테스트 시나리오, 복수개의 테스트 케이스가 존재한다. 단위 테스트 및 통합 테스트는 모든 정의 사항 및 모든 시나리오 / 케이스에 대해 수행되어야 한다.

### 4. 제약 및 규칙 (Constraints)

* 명제형 서술: '~한다', '~확인' 등으로 명확히 종결한다.
* 전문 용어: 청약, 심사, 배서 등 도메인 용어를 정확히 사용한다.
* 경계값 분석: 기획안 내 숫자가 있는 경우 경계값 테스트를 반드시 포함한다.
* Screen Definition에 없더라도 청약 설계 시스템 구조 상 테스트 필요한 조건이 있는 경우 반영하여 작성한다.
* 논리적 근거: [원칙 + 예외 + 이유] 구조를 유지한다.

### 5. 응대 태도 (Tone & Manner)

* 서론과 결론 없이 핵심 내용만 간결하게 전달한다.
* 전문적이고 분석적인 태도를 유지한다.
* JSON 형식을 엄격히 준수한다.

최소 15개 이상의 테스트 케이스를 생성하며, Positive Case와 Negative Case를 균형있게 포함한다.
"""

# ---------- 유틸리티 함수들 ----------

def encode_image_to_base64(uploaded_file) -> str:
    """
    업로드된 이미지 파일을 Base64 문자열로 인코딩
    
    Args:
        uploaded_file: Streamlit의 UploadedFile 객체
    
    Returns:
        str: Base64로 인코딩된 이미지 문자열
    """
    # 업로드된 파일의 바이트 데이터를 읽음
    bytes_data = uploaded_file.getvalue()
    # Base64로 인코딩하고 UTF-8 문자열로 디코딩하여 반환
    return base64.b64encode(bytes_data).decode('utf-8')

def call_gemini_api(api_key: str, image_base64: str, model_name: str = "models/gemini-2.5-flash") -> str:
    """
    Google Gemini API를 호출하여 이미지 분석 및 테스트 시나리오 생성
    
    Args:
        api_key: Google AI Studio에서 발급받은 API 키
        image_base64: Base64로 인코딩된 이미지 데이터
        model_name: 사용할 Gemini 모델명 (기본값: models/gemini-2.5-flash)
    
    Returns:
        str: LLM이 생성한 JSON 형식의 테스트 시나리오
    """
    try:
        # Gemini API 설정 (API 키 등록)
        genai.configure(api_key=api_key)
        
        # 모델 인스턴스 생성
        model = genai.GenerativeModel(model_name)
        
        # 이미지 데이터를 Gemini가 이해할 수 있는 형식으로 변환
        image_part = {
            "mime_type": "image/jpeg",  # MIME 타입 지정
            "data": image_base64  # Base64 인코딩된 이미지 데이터
        }
        
        # 프롬프트와 이미지를 함께 전송하여 콘텐츠 생성 요청
        response = model.generate_content([SYSTEM_PROMPT, image_part])
        
        # 생성된 텍스트 응답 반환
        return response.text
        
    except Exception as e:
        # API 호출 실패 시 예외를 상위로 전파
        raise Exception(f"Gemini API 호출 실패: {str(e)}")

def parse_json_response(response_text: str) -> List[dict]:
    """
    LLM 응답 텍스트를 파싱하여 테스트 시나리오 리스트로 변환
    
    Args:
        response_text: LLM이 반환한 JSON 문자열
    
    Returns:
        List[dict]: 파싱된 테스트 시나리오 딕셔너리 리스트
    """
    try:
        # Markdown 코드 블록 제거 (LLM이 ```json ... ``` 형식으로 응답할 경우 대비)
        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```json"):
            # 시작 부분의 ```json 제거
            cleaned_text = cleaned_text[7:]
        if cleaned_text.startswith("```"):
            # 시작 부분의 ``` 제거
            cleaned_text = cleaned_text[3:]
        if cleaned_text.endswith("```"):
            # 끝 부분의 ``` 제거
            cleaned_text = cleaned_text[:-3]
        
        # JSON 파싱
        cleaned_text = cleaned_text.strip()
        parsed_data = json.loads(cleaned_text)
        
        # Pydantic 모델로 검증 (새로운 TestCaseList 모델 사용)
        test_case_list = TestCaseList(**parsed_data)
        
        # 딕셔너리 리스트로 변환하여 반환 (Pydantic v2)
        return [test_case.model_dump() for test_case in test_case_list.test_cases]
        
    except json.JSONDecodeError as e:
        # JSON 파싱 실패 시 예외 발생
        raise Exception(f"JSON 파싱 오류: {str(e)}\n원본 텍스트:\n{response_text}")
    except Exception as e:
        # 기타 예외 발생 시
        raise Exception(f"데이터 변환 오류: {str(e)}")

def create_excel_file(df: pd.DataFrame) -> BytesIO:
    """
    DataFrame을 포맷팅된 Excel 파일로 변환
    
    Args:
        df: 테스트 시나리오가 담긴 DataFrame
    
    Returns:
        BytesIO: 메모리 상의 Excel 파일 객체
    """
    # 메모리 상에 바이너리 파일 객체 생성
    output = BytesIO()
    
    # openpyxl 엔진을 사용하여 Excel 파일 작성
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # DataFrame을 Excel 시트로 작성 (인덱스 제외)
        df.to_excel(writer, index=False, sheet_name='테스트 시나리오')
        
        # 워크북과 워크시트 객체 가져오기
        workbook = writer.book
        worksheet = writer.sheets['테스트 시나리오']
        
        # 컬럼 너비 자동 조정
        for idx, col in enumerate(df.columns):
            # 각 컬럼의 최대 길이 계산 (헤더와 데이터 중 긴 것)
            max_length = max(
                df[col].astype(str).apply(len).max(),  # 데이터 최대 길이
                len(col)  # 헤더 길이
            )
            # 최대 길이에 여유분 추가하여 컬럼 너비 설정 (최대 50)
            worksheet.column_dimensions[chr(65 + idx)].width = min(max_length + 5, 50)
        
        # 헤더 행 스타일 적용 (Bold, 배경색)
        from openpyxl.styles import Font, PatternFill, Alignment
        
        header_font = Font(bold=True, color="FFFFFF")  # 굵은 흰색 글씨
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")  # 파란색 배경
        header_alignment = Alignment(horizontal="center", vertical="center")  # 중앙 정렬
        
        # 첫 번째 행(헤더)에 스타일 적용
        for cell in worksheet[1]:
            cell.font = header_font  # 폰트 적용
            cell.fill = header_fill  # 배경색 적용
            cell.alignment = header_alignment  # 정렬 적용
        
        # 모든 셀에 텍스트 줄바꿈 적용
        for row in worksheet.iter_rows(min_row=2, max_row=worksheet.max_row):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")  # 자동 줄바꿈 및 상단 정렬
    
    # 파일 포인터를 시작 위치로 이동
    output.seek(0)
    return output

# ---------- CSS 로딩 함수 ----------

def load_custom_css():
    """
    커스텀 CSS 파일을 로드하여 Streamlit 앱에 적용
    
    style.css 파일이 존재하면 로드하고, 없으면 기본 스타일 적용
    """
    # CSS 파일 경로 생성 (현재 스크립트와 동일한 디렉토리)
    css_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.css")
    
    # CSS 파일이 존재하는지 확인
    if os.path.exists(css_file_path):
        # 파일을 읽어서 Streamlit에 적용
        with open(css_file_path, encoding='utf-8') as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    else:
        # CSS 파일이 없을 경우 기본 스타일 적용
        st.warning("⚠️ style.css 파일을 찾을 수 없습니다. 기본 스타일이 적용됩니다.")

# ---------- 히스토리 관리 함수들 ----------

def get_history_file_path() -> str:
    """
    히스토리 CSV 파일의 경로를 반환
    
    Returns:
        str: history.csv 파일의 절대 경로
    """
    # 현재 스크립트 파일이 있는 디렉토리 경로 가져오기
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # history.csv 파일 경로 생성
    return os.path.join(current_dir, "history.csv")

def load_history() -> pd.DataFrame:
    """
    히스토리 파일을 로드하여 DataFrame으로 반환
    
    Returns:
        pd.DataFrame: 히스토리 데이터 (파일이 없으면 빈 DataFrame)
    """
    # 히스토리 파일 경로 가져오기
    history_path = get_history_file_path()
    
    # 기본 컬럼 정의 (버전 관리 추가)
    default_columns = ['Timestamp', 'Model', 'ImageName', 'ScenarioCount', 'Scenarios', 'Version', 'ParentID']
    
    # 파일이 존재하는지 확인
    if os.path.exists(history_path):
        try:
            # CSV 파일을 DataFrame으로 로드
            df = pd.read_csv(history_path, encoding='utf-8-sig')
            # Version 컬럼이 없으면 추가 (기존 데이터 호환)
            if 'Version' not in df.columns:
                df['Version'] = 'v1'
            if 'ParentID' not in df.columns:
                df['ParentID'] = ''
            return df
        except Exception as e:
            # 파일 로드 실패 시 빈 DataFrame 반환
            st.warning(f"히스토리 파일 로드 중 오류: {str(e)}")
            return pd.DataFrame(columns=default_columns)
    else:
        # 파일이 없으면 빈 DataFrame 반환
        return pd.DataFrame(columns=default_columns)

def save_to_history(model_name: str, image_name: str, scenarios: List[dict], version: str = "v1", parent_id: str = ""):
    """
    생성된 시나리오를 히스토리 파일에 저장
    
    Args:
        model_name: 사용한 모델명
        image_name: 업로드한 이미지 파일명
        scenarios: 생성된 시나리오 리스트
        version: 버전 태그 (v1=1차 생성, v2=2차 검수, Final=최종본)
        parent_id: 부모 히스토리 ID (2차 검수 시 원본 참조)
    """
    try:
        # 현재 시간 가져오기 (한국 시간 기준)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 시나리오를 JSON 문자열로 변환 (저장용)
        scenarios_json = json.dumps(scenarios, ensure_ascii=False)
        
        # 새로운 히스토리 엔트리 생성
        new_entry = pd.DataFrame([{
            'Timestamp': timestamp,
            'Model': model_name,
            'ImageName': image_name,
            'ScenarioCount': len(scenarios),
            'Scenarios': scenarios_json,
            'Version': version,
            'ParentID': parent_id
        }])
        
        # 기존 히스토리 로드
        history_df = load_history()
        
        # 새 엔트리를 기존 히스토리에 추가 (최신 것이 위로)
        updated_history = pd.concat([new_entry, history_df], ignore_index=True)
        
        # 히스토리 파일에 저장
        history_path = get_history_file_path()
        updated_history.to_csv(history_path, index=False, encoding='utf-8-sig')
        
        return True
    except Exception as e:
        # 저장 실패 시 에러 메시지 표시
        st.error(f"히스토리 저장 중 오류 발생: {str(e)}")
        return False

def delete_history_entry(index: int):
    """
    특정 히스토리 엔트리 삭제
    
    Args:
        index: 삭제할 엔트리의 인덱스
    """
    try:
        # 히스토리 로드
        history_df = load_history()
        
        # 해당 인덱스 행 삭제
        if 0 <= index < len(history_df):
            history_df = history_df.drop(index).reset_index(drop=True)
            
            # 파일에 저장
            history_path = get_history_file_path()
            history_df.to_csv(history_path, index=False, encoding='utf-8-sig')
            
            return True
        return False
    except Exception as e:
        st.error(f"히스토리 삭제 중 오류: {str(e)}")
        return False

# ---------- Streamlit UI 구성 ----------

def main():
    """메인 애플리케이션 함수"""
    
    # 페이지 기본 설정
    st.set_page_config(
        page_title="테스트 시나리오 생성기 2.0",  # 브라우저 탭 제목
        page_icon="📋",  # 파비콘 - 이모지 대신 간단한 아이콘
        layout="wide",  # 와이드 레이아웃 사용
        initial_sidebar_state="expanded"  # 사이드바 기본 확장
    )
    
    # 커스텀 CSS 로드
    load_custom_css()
    
    # 메인 타이틀 - 깔끔한 텍스트 버전
    st.markdown("""
        <div style='text-align: center; padding: 2rem 0; margin-bottom: 2rem;'>
            <h1 style='font-size: 3rem; margin-bottom: 0.5rem; color: #6f42c1;'>
                테스트 시나리오 자동 생성기 v2.0
            </h1>
            <p style='font-size: 1.2rem; color: #6c757d; font-weight: 400;'>
                AI 기반 화면 설계서 분석 · 테스트 케이스 자동화 · 엔터프라이즈 QA 솔루션
            </p>
            <p style='font-size: 0.95rem; color: #adb5bd; margin-top: 0.5rem;'>
                Powered by Google Gemini 2.5 | Premium Edition by 토리고니
             </p>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")  # 구분선
    
    # ---------- 사이드바: API 설정 ----------
    with st.sidebar:
        # 사이드바 헤더 - 로고 스타일
        st.markdown("""
            <div style='text-align: center; padding: 1.5rem 0; margin-bottom: 2rem; 
                        border-bottom: 2px solid #dee2e6;'>
                <h2 style='margin: 0; font-size: 1.5rem; color: #6f42c1;'>설정</h2>
                <p style='color: #6c757d; font-size: 0.85rem; margin-top: 0.5rem;'>
                    Configuration & Settings
                </p>
            </div>
        """, unsafe_allow_html=True)
        
        # API 키 입력 필드 (비밀번호 타입으로 숨김 처리)
        st.markdown("### 🔑 API 인증")
        api_key = st.text_input(
            "Google Gemini API Key",
            type="password",  # 입력값 숨김 처리
            help="Google AI Studio에서 발급받은 API 키를 입력하세요.",
            placeholder="AIza..."
        )
        
        # API 키 상태 표시
        if api_key:
            st.success("✅ API 키가 설정되었습니다")
        else:
            st.info("💡 API 키를 입력하여 시작하세요")
        
        st.markdown("---")
        
        # 모델 선택 드롭다운
        st.markdown("### 🤖 AI 모델 선택")
        
        # 모델 그룹핑 및 추천 표시
        model_options = {
            "🌟 추천 모델 (빠름 + 정확)": [
                "models/gemini-2.5-flash",
                "models/gemini-2.5-pro",
            ],
            "⚡ Flash 시리즈 (초고속)": [
                "models/gemini-2.0-flash-exp",
                "models/gemini-2.0-flash",
                "models/gemini-2.0-flash-001",
            ],
            "💎 Pro 시리즈 (고정밀)": [
                "models/gemini-3-pro-preview",
                "models/gemini-pro-latest",
            ],
            "🪶 Lite 시리즈 (경량)": [
                "models/gemini-2.0-flash-lite",
                "models/gemini-2.0-flash-lite-001",
                "models/gemini-flash-lite-latest",
            ],
            "🧪 실험 모델": [
                "models/gemini-exp-1206",
                "models/gemini-2.0-flash-exp-image-generation",
            ]
        }
        
        # 플랫 리스트로 변환
        all_models = []
        for models in model_options.values():
            all_models.extend(models)
        
        model_name = st.selectbox(
            "모델 선택",
            all_models,
            index=0,  # 기본값: gemini-2.5-flash (최신 Flash 모델)
            help="사용할 Gemini 모델을 선택하세요. Flash는 빠르고 비용 효율적이며, Pro는 정확도가 높습니다."
        )
        
        # 선택된 모델 정보 표시
        if "flash" in model_name.lower():
            st.markdown("⚡ **특성:** 빠른 응답 속도, 비용 효율적")
        elif "pro" in model_name.lower():
            st.markdown("💎 **특성:** 높은 정확도, 복잡한 분석")
        elif "lite" in model_name.lower():
            st.markdown("🪶 **특성:** 경량화, 저비용")
        
        st.markdown("---")  # 구분선
        
        # 사용 방법 가이드
        st.markdown("### 📖 사용 가이드")
        
        with st.expander("🚀 빠른 시작", expanded=False):
            st.markdown("""
            1. **API 키** 입력
            2. **이미지** 업로드
            3. **시나리오 생성** 클릭
            4. **Excel** 다운로드
            """)
        
        with st.expander("📚 히스토리 활용", expanded=False):
            st.markdown("""
            - 생성된 시나리오 자동 저장
            - 히스토리 탭에서 조회
            - 이전 결과 불러오기
            - 불필요한 항목 삭제
            """)
        
        with st.expander("💡 팁 & 트릭", expanded=False):
            st.markdown("""
            - **선명한 이미지** 사용 권장
            - **설명 텍스트** 포함 시 정확도 ↑
            - **Flash 모델**: 일반 케이스
            - **Pro 모델**: 복잡한 화면
            """)
        
        st.markdown("---")
        
        # 히스토리 퀵 스탯
        history_df = load_history()
        if len(history_df) > 0:
            st.markdown("### 📊 통계")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("총 생성", f"{len(history_df)}")
            with col2:
                total_scenarios = history_df['ScenarioCount'].sum() if 'ScenarioCount' in history_df.columns else 0
                st.metric("시나리오", f"{total_scenarios}")
        
        # 버전 정보
        st.markdown("---")
        st.markdown("""
            <div style='text-align: center; color: #65676b; font-size: 0.8rem; padding: 1rem 0;'>
                <p style='margin: 0;'>Test Scenario Generator</p>
                <p style='margin: 0.25rem 0;'><strong>v2.0 Premium by 토리고니</strong></p>
                <p style='margin: 0.25rem 0;'>© 2026 Enterprise QA Solution</p>
            </div>
        """, unsafe_allow_html=True)
    
    # ---------- 탭 구성: 시나리오 생성 / 히스토리 ----------
    tab1, tab2, tab3 = st.tabs(["🚀 시나리오 생성", "📚 히스토리", "🔍 2차 QA 검수"])
    
    # ========== 탭 1: 시나리오 생성 ==========
    with tab1:
        # ---------- 메인 영역: 이미지 업로드 ----------
        st.markdown("### 1️⃣ 화면 설계서 업로드")
        st.markdown("화면 설계서 이미지를 업로드하여 AI가 분석하도록 합니다. **여러 파일을 한 번에 선택할 수 있습니다.**")
        
        # 파일 업로더 컴포넌트 (다중 파일 지원)
        uploaded_files = st.file_uploader(
            "이미지 선택",
            type=["png", "jpg", "jpeg"],  # 허용 파일 확장자
            help="📷 PNG, JPG, JPEG 형식의 화면 설계서 이미지를 업로드하세요. Ctrl/Cmd 키로 여러 파일 선택 가능",
            label_visibility="collapsed",  # 라벨 숨기기
            accept_multiple_files=True  # 다중 파일 업로드 활성화
        )
        
        # 업로드 상태에 따른 메시지
        if uploaded_files:
            # 업로드 성공 - 파일 목록 표시
            st.success(f"✅ **{len(uploaded_files)}개** 파일 업로드 완료")
            
            # 파일 목록을 Expander로 표시
            with st.expander(f"📁 업로드된 파일 목록 ({len(uploaded_files)}개)", expanded=len(uploaded_files) <= 3):
                for idx, file in enumerate(uploaded_files, 1):
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        st.write(f"{idx}. **{file.name}**")
                    with col2:
                        file_size = file.size / 1024
                        if file_size < 1024:
                            st.caption(f"📦 {file_size:.1f} KB")
                        else:
                            st.caption(f"📦 {file_size/1024:.1f} MB")
                    with col3:
                        st.caption(f"🖼️ {file.type.split('/')[-1].upper()}")
            
            # 첫 번째 이미지 미리보기
            if len(uploaded_files) == 1:
                try:
                    image = Image.open(uploaded_files[0])
                    st.image(image, caption=f"업로드된 화면 설계서: {uploaded_files[0].name}", use_container_width=True)
                except:
                    st.warning("⚠️ 이미지 미리보기를 표시할 수 없습니다.")
            else:
                st.info(f"💡 {len(uploaded_files)}개의 이미지가 업로드되었습니다. 생성 버튼을 클릭하면 모든 이미지를 순차적으로 분석합니다.")
        else:
            # 업로드 전 안내 메시지
            st.info("""
            **💡 업로드 가이드:**
            - 화면 설계서, UI 목업, 화면 정의서 등을 업로드하세요
            - 텍스트가 선명하게 보이는 이미지를 사용하면 정확도가 높아집니다
            - Description이나 설명이 포함된 이미지가 가장 좋습니다
            - **Ctrl(Windows) 또는 Cmd(Mac) 키를 누른 채로 여러 파일을 선택**할 수 있습니다
            """)
    
        # ---------- 시나리오 생성 버튼 (탭1 안에) ----------
        st.markdown("---")
        st.markdown("### 2️⃣ AI 시나리오 생성")
        st.markdown("업로드한 화면 설계서를 AI가 분석하여 테스트 시나리오를 자동으로 생성합니다.")
        
        # 생성 버튼
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            generate_button = st.button(
                "🚀 AI 시나리오 생성 시작",
                use_container_width=True,
                type="primary",
                help="클릭하여 AI가 테스트 시나리오를 생성하도록 합니다"
            )
    
    # ---------- 시나리오 생성 로직 ----------
    if generate_button:
        # 1) API 키 검증
        if not api_key:
            st.error("❌ API 키를 입력해주세요!")
            st.stop()
        
        # 2) 이미지 업로드 검증
        if not uploaded_files:
            st.error("❌ 이미지를 업로드해주세요!")
            st.stop()
        
        # 3) 다중 이미지 처리
        total_files = len(uploaded_files)
        all_scenarios = []  # 모든 시나리오를 저장할 리스트
        
        # 진행률 바와 상태 표시
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, uploaded_file in enumerate(uploaded_files):
            # 현재 처리 중인 파일 표시
            current_progress = (idx) / total_files
            progress_bar.progress(current_progress)
            status_text.info(f"🔍 처리 중: {idx + 1}/{total_files} - **{uploaded_file.name}**")
            
            try:
                # 3-1) 이미지 Base64 인코딩
                image_base64 = encode_image_to_base64(uploaded_file)
                
                # 3-2) LLM API 호출 (재시도 로직 포함)
                response_text = None
                retry_count = 0
                max_retries = 1
                
                while retry_count <= max_retries:
                    try:
                        response_text = call_gemini_api(api_key, image_base64, model_name)
                        break
                    except Exception as api_error:
                        retry_count += 1
                        if retry_count > max_retries:
                            raise api_error
                        time.sleep(1)
                
                # 3-3) JSON 파싱
                try:
                    scenarios = parse_json_response(response_text)
                    all_scenarios.extend(scenarios)  # 결과 누적
                    
                    # 개별 파일 히스토리 저장
                    save_to_history(model_name, uploaded_file.name, scenarios)
                    
                except Exception as parse_error:
                    st.error(f"❌ {uploaded_file.name} 파싱 오류: {str(parse_error)}")
                    st.warning(f"⚠️ {uploaded_file.name}을(를) 건너뜁니다.")
                    continue
                    
            except Exception as e:
                st.error(f"❌ {uploaded_file.name} 처리 실패: {str(e)}")
                st.warning(f"⚠️ {uploaded_file.name}을(를) 건너뛰고 계속 진행합니다.")
                continue
        
        # 처리 완료
        progress_bar.progress(1.0)
        status_text.empty()
        
        # 4) 결과 처리
        if all_scenarios:
            # DataFrame 생성
            df = pd.DataFrame(all_scenarios)
            
            # 세션 스테이트에 저장
            st.session_state['df_result'] = df
            st.session_state['uploaded_image'] = uploaded_files[0] if len(uploaded_files) == 1 else None
            
            # 성공 메시지
            st.success(f"✅ 총 **{total_files}개 파일**에서 **{len(all_scenarios)}개**의 테스트 케이스가 생성되었습니다!")
            st.balloons()  # 축하 애니메이션
        else:
            st.error("❌ 시나리오 생성에 실패했습니다. 모든 파일 처리 중 오류가 발생했습니다.")
            st.stop()
    
    # ---------- 결과 표시 영역 ----------
    if 'df_result' in st.session_state and st.session_state['df_result'] is not None:
        st.markdown("---")  # 구분선
        
        # 결과 섹션 헤더
        st.markdown("""
            <div style='text-align: center; margin: 2rem 0;'>
                <h2 style='font-size: 2rem; margin-bottom: 0.5rem;'>
                    ✨ 생성된 테스트 시나리오
                </h2>
                <p style='color: #b0b3b8; font-size: 1rem;'>
                    AI가 분석한 결과를 확인하고 Excel로 다운로드하세요
                </p>
            </div>
        """, unsafe_allow_html=True)
        
        # 2단 컬럼 레이아웃: 좌측(이미지) + 우측(테이블)
        col_left, col_right = st.columns([1, 2], gap="large")
        
        with col_left:
            st.markdown("#### 📷 원본 화면 설계서")
            # 업로드된 이미지가 있는지 확인 (히스토리에서 불러온 경우 None일 수 있음)
            if st.session_state.get('uploaded_image') is not None:
                # 업로드된 이미지 표시
                image = Image.open(st.session_state['uploaded_image'])
                st.image(image, use_container_width=True)  # 컬럼 너비에 맞춤
            else:
                # 이미지가 없을 경우 (히스토리에서 불러온 경우)
                st.info("""
                📭 **히스토리에서 불러온 시나리오**
                
                원본 이미지는 저장되지 않습니다.
                생성된 테스트 케이스만 확인 가능합니다.
                """)
        
        with col_right:
            st.markdown("#### 📋 테스트 시나리오 목록")
            
            # 시나리오 개수 표시
            st.markdown(f"""
                <div style='background: rgba(102, 126, 234, 0.1); padding: 0.75rem 1rem; 
                            border-radius: 8px; margin-bottom: 1rem; border-left: 4px solid #667eea;'>
                    <strong>총 {len(st.session_state['df_result'])}개</strong>의 테스트 시나리오가 생성되었습니다
                </div>
            """, unsafe_allow_html=True)
            
            # DataFrame을 인터랙티브 테이블로 표시
            st.dataframe(
                st.session_state['df_result'],
                use_container_width=True,  # 컬럼 너비에 맞춤
                height=600  # 테이블 높이 고정
            )
        
        # ---------- Excel 다운로드 버튼 ----------
        st.markdown("---")  # 구분선
        st.markdown("#### 💾 결과 다운로드")
        
        # Excel 파일 생성
        excel_file = create_excel_file(st.session_state['df_result'])
        
        # 다운로드 버튼 (중앙 정렬 + 크게)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.download_button(
                label="📥 Excel 파일 다운로드",
                data=excel_file,  # 바이너리 데이터
                file_name=f"테스트_시나리오_{time.strftime('%Y%m%d_%H%M%S')}.xlsx",  # 타임스탬프 포함 파일명
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # Excel MIME 타입
                use_container_width=True,  # 컬럼 너비에 맞춤
                type="primary"  # 강조 버튼 스타일
            )
            st.caption("📊 실무 서식으로 포맷팅된 Excel 파일이 다운로드됩니다")
        
        # Happy/Exception Path 통계 표시
        st.markdown("---")
        st.markdown("#### 📊 시나리오 분석 통계")
        
        # 4단 컬럼으로 통계 표시
        stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
        
        with stat_col1:
            # 전체 시나리오 개수
            st.metric(
                "전체 시나리오", 
                f"{len(st.session_state['df_result'])}개",
                help="생성된 총 테스트 시나리오 수"
            )
        
        with stat_col2:
            # 중요도별 카운트
            if '중요도' in st.session_state['df_result'].columns:
                high_count = len(st.session_state['df_result'][st.session_state['df_result']['중요도'] == '상'])
                st.metric(
                    "중요도 '상'", 
                    f"{high_count}개",
                    delta=f"{high_count/len(st.session_state['df_result'])*100:.0f}%",
                    help="높은 우선순위 테스트 케이스"
                )
        
        with stat_col3:
            # 대분류별 카운트
            if '대분류' in st.session_state['df_result'].columns:
                func_count = len(st.session_state['df_result'][st.session_state['df_result']['대분류'] == '기능'])
                st.metric(
                    "기능 테스트", 
                    f"{func_count}개",
                    help="기능 관련 테스트 케이스"
                )
        
        with stat_col4:
            # UI 테스트 카운트
            if '대분류' in st.session_state['df_result'].columns:
                ui_count = len(st.session_state['df_result'][st.session_state['df_result']['대분류'] == 'UI'])
                st.metric(
                    "UI 테스트", 
                    f"{ui_count}개",
                    help="UI 관련 테스트 케이스"
                )
    
    # ========== 탭 2: 히스토리 ==========
    with tab2:
        # 히스토리 헤더
        st.markdown("""
            <div style='text-align: center; margin-bottom: 2rem;'>
                <h2 style='font-size: 2rem; margin-bottom: 0.5rem;'>
                    📚 테스트 시나리오 히스토리
                </h2>
                <p style='color: #b0b3b8; font-size: 1rem;'>
                    이전에 생성한 테스트 시나리오 목록을 조회하고 다시 불러올 수 있습니다
                </p>
            </div>
        """, unsafe_allow_html=True)
        
        # 히스토리 데이터 로드
        history_df = load_history()
        
        # 히스토리가 있는지 확인
        if len(history_df) > 0:
            # 히스토리 통계
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("📊 총 기록", f"{len(history_df)}")
            with col2:
                total_scenarios = history_df['ScenarioCount'].sum() if 'ScenarioCount' in history_df.columns else 0
                st.metric("📋 전체 시나리오", f"{total_scenarios}")
            with col3:
                if len(history_df) > 0:
                    latest = history_df.iloc[0]['Timestamp']
                    st.metric("🕒 최근 생성", latest.split()[0])
            with col4:
                unique_models = history_df['Model'].nunique() if 'Model' in history_df.columns else 0
                st.metric("🤖 사용 모델", f"{unique_models}종")
            
            st.markdown("---")
            
            # 통합 다운로드 기능
            st.markdown("### 📦 통합 다운로드")
            st.markdown("체크박스로 여러 항목을 선택하여 하나의 Excel 파일로 다운로드할 수 있습니다.")
            
            # 세션 상태 초기화 (히스토리 개수가 변경되면 재초기화)
            if 'history_selections' not in st.session_state or len(st.session_state['history_selections']) != len(history_df):
                st.session_state['history_selections'] = [False] * len(history_df)
            
            # 표시용 DataFrame 생성 (선택 컬럼 추가)
            display_df = history_df.copy()
            display_df.insert(0, '선택', st.session_state['history_selections'])
            
            # 전체 선택/해제 버튼
            col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
            with col_btn1:
                if st.button("✅ 전체 선택", use_container_width=True):
                    st.session_state['history_selections'] = [True] * len(history_df)
                    st.rerun()
            with col_btn2:
                if st.button("❎ 전체 해제", use_container_width=True):
                    st.session_state['history_selections'] = [False] * len(history_df)
                    st.rerun()
            
            # 편집 가능한 표로 표시
            st.markdown("**📋 히스토리 목록** (체크박스를 클릭하여 선택)")
            edited_df = st.data_editor(
                display_df,
                column_config={
                    "선택": st.column_config.CheckboxColumn(
                        "선택",
                        help="통합 다운로드할 항목 선택",
                        default=False,
                    ),
                    "Timestamp": st.column_config.TextColumn("생성 시간", width="medium"),
                    "Model": st.column_config.TextColumn("모델", width="small"),
                    "ImageName": st.column_config.TextColumn("이미지/설명", width="medium"),
                    "ScenarioCount": st.column_config.NumberColumn("시나리오 수", width="small"),
                    "Version": st.column_config.TextColumn("버전", width="small"),
                },
                hide_index=True,
                use_container_width=True,
                disabled=["Timestamp", "Model", "ImageName", "ScenarioCount", "Scenarios", "Version", "ParentID"],
                key="history_table"
            )
            
            # 편집된 선택 상태를 세션에 저장
            st.session_state['history_selections'] = edited_df['선택'].tolist()
            
            # 선택된 항목 확인
            selected_indices = edited_df[edited_df['선택'] == True].index.tolist()
            
            # 선택 정보 표시
            if len(selected_indices) > 0:
                st.info(f"📌 **{len(selected_indices)}개 항목** 선택됨")
                
                # 통합 다운로드 버튼
                consolidated_scenarios = []
                for idx in selected_indices:
                    row = history_df.iloc[idx]
                    try:
                        scenarios = json.loads(row['Scenarios'])
                        consolidated_scenarios.extend(scenarios)
                    except:
                        pass
                
                if consolidated_scenarios:
                    # DataFrame 생성
                    consolidated_df = pd.DataFrame(consolidated_scenarios)
                    
                    # Excel 파일 생성
                    excel_file = create_excel_file(consolidated_df)
                    
                    # 다운로드 버튼
                    col_dl1, col_dl2, col_dl3 = st.columns([1, 2, 1])
                    with col_dl2:
                        st.download_button(
                            label=f"📥 선택한 {len(selected_indices)}개 항목 통합 다운로드 ({len(consolidated_scenarios)}개 케이스)",
                            data=excel_file,
                            file_name=f"통합_테스트케이스_{time.strftime('%Y%m%d_%H%M%S')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            type="primary"
                        )
            
            st.markdown("---")
            
            # 상세 보기 및 액션 - 기본적으로 접힌 상태
            with st.expander("📜 상세 보기 및 액션", expanded=False):
                # 히스토리 상세 보기 (Expander로)
                for idx, row in history_df.iterrows():
                    with st.expander(
                        f"🕒 {row['Timestamp']} | 📷 {row['ImageName']} | 📋 {row['ScenarioCount']}개 시나리오",
                        expanded=False
                    ):
                        # 히스토리 상세 정보
                        info_col1, info_col2, action_col = st.columns([2, 2, 1])
                        
                        with info_col1:
                            st.markdown(f"""
                                **🤖 사용 모델:**  
                                `{row['Model']}`
                                
                                **📷 이미지 파일:**  
                                `{row['ImageName']}`
                            """)
                        
                        with info_col2:
                            st.markdown(f"""
                                **🕒 생성 시간:**  
                                `{row['Timestamp']}`
                                
                                **📊 시나리오 수:**  
                                `{row['ScenarioCount']}개`
                            """)
                        
                        with action_col:
                            st.markdown("**⚡ 액션**")
                            # 불러오기 버튼
                            if st.button(f"📥 불러오기", key=f"load_{idx}", use_container_width=True):
                                try:
                                    scenarios = json.loads(row['Scenarios'])
                                    df = pd.DataFrame(scenarios)
                                    st.session_state['df_result'] = df
                                    st.session_state['uploaded_image'] = None
                                    st.success(f"✅ '{row['ImageName']}'의 시나리오를 불러왔습니다!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"시나리오 불러오기 실패: {str(e)}")
                            
                            # 삭제 버튼
                            if st.button(f"🗑️ 삭제", key=f"delete_{idx}", use_container_width=True, type="secondary"):
                                if delete_history_entry(idx):
                                    st.success("✅ 히스토리가 삭제되었습니다!")
                                    st.rerun()
                                else:
                                    st.error("❌ 삭제에 실패했습니다.")
                        
                        # 구분선
                        st.markdown("---")
                        
                        # 시나리오 미리보기
                        st.markdown("**📋 시나리오 미리보기** (처음 3개)")
                        try:
                            scenarios = json.loads(row['Scenarios'])
                            preview_df = pd.DataFrame(scenarios[:3])
                            st.dataframe(preview_df, use_container_width=True, height=200)
                            if len(scenarios) > 3:
                                st.caption(f"💡 {len(scenarios) - 3}개의 시나리오가 더 있습니다. 불러오기를 클릭하여 전체 보기")
                        except:
                            st.warning("⚠️ 미리보기를 표시할 수 없습니다.")
        else:
            # 히스토리가 없을 때
            st.markdown("""
                <div style='text-align: center; padding: 4rem 2rem;'>
                    <div style='font-size: 4rem; margin-bottom: 1rem;'>📭</div>
                    <h3 style='color: #b0b3b8; margin-bottom: 1rem;'>
                        아직 저장된 히스토리가 없습니다
                    </h3>
                    <p style='color: #65676b; font-size: 1rem; margin-bottom: 2rem;'>
                        시나리오를 생성하면 자동으로 히스토리에 저장됩니다.<br>
                        언제든지 이곳에서 이전 결과를 다시 확인하고 불러올 수 있습니다.
                    </p>
                    <p style='color: #667eea; font-size: 0.9rem;'>
                        💡 "시나리오 생성" 탭에서 첫 번째 시나리오를 만들어보세요!
                    </p>
                </div>
            """, unsafe_allow_html=True)
    
    # ========== 탭 3: 2차 QA 검수 ==========
    with tab3:
        # 헤더
        st.markdown("""
            <div style='text-align: center; margin-bottom: 2rem;'>
                <h2 style='font-size: 2rem; margin-bottom: 0.5rem;'>
                    🔍 2차 QA 검수 - 비즈니스 조건 확장
                </h2>
                <p style='color: #b0b3b8; font-size: 1rem;'>
                    기존 테스트 케이스에 보험 계약 조건을 추가하여 확장된 테스트 케이스를 생성합니다
                </p>
            </div>
        """, unsafe_allow_html=True)
        
        # 좌우 2단 구조
        left_col, right_col = st.columns([4, 6])
        
        with left_col:
            st.markdown("### 📋 비즈니스 조건 선택")
            
            # 1. 계약자 속성
            with st.expander("👤 계약자 속성", expanded=True):
                contractor_age = st.multiselect(
                    "연령",
                    ["성인", "미성년자"],
                    help="계약자의 연령대 선택"
                )
                contractor_nationality = st.multiselect(
                    "국적",
                    ["내국인", "외국인"],
                    help="계약자의 국적"
                )
                contractor_occupation = st.multiselect(
                    "직업",
                    ["일반직", "위험직", "무직"],
                    help="계약자의 직업 분류"
                )
                contractor_income = st.multiselect(
                    "월소득",
                    ["100만원 이하", "100-300만원", "300-500만원", "500만원 이상"],
                    help="계약자의 월소득 구간"
                )
            
            # 2. 피보험자 속성
            with st.expander("🧑 피보험자 속성", expanded=True):
                insured_age = st.multiselect(
                    "연령 ",  # 공백으로 구분 (키 중복 방지)
                    ["성인", "미성년자"],
                    key="insured_age",
                    help="피보험자의 연령대 선택"
                )
                insured_nationality = st.multiselect(
                    "국적 ",
                    ["내국인", "외국인"],
                    key="insured_nationality",
                    help="피보험자의 국적"
                )
                insured_occupation = st.multiselect(
                    "직업 ",
                    ["일반직", "위험직", "무직"],
                    key="insured_occupation",
                    help="피보험자의 직업 분류"
                )
            
            # 3. 상품 구성
            with st.expander("📦 상품 구성", expanded=True):
                product_main = st.multiselect(
                    "주계약",
                    ["종신보험", "정기보험", "연금보험"],
                    help="주계약 종류"
                )
                product_riders = st.multiselect(
                    "특약",
                    ["건강특약", "상해특약", "재해특약", "특약없음"],
                    help="부가 특약"
                )
            
            # 4. 계약관계인
            with st.expander("👥 계약관계인", expanded=False):
                beneficiary_maturity = st.checkbox("만기수익자 지정")
                beneficiary_hospitalization = st.checkbox("입원상해수익자 지정")
                beneficiary_death = st.checkbox("사망시수익자 지정")
                beneficiary_dementia = st.checkbox("치매수익자 지정")
                proxy_designee = st.checkbox("지정대리청구인 지정")
            
            # 5. 계약 상태
            with st.expander("📝 계약 상태", expanded=False):
                application_type = st.multiselect(
                    "청약방식",
                    ["서면청약", "전자청약", "모바일청약"],
                    help="청약 방식"
                )
                payment_method = st.multiselect(
                    "납입방법",
                    ["월납", "연납", "일시납"],
                    help="보험료 납입 방법"
                )
                payment_period = st.multiselect(
                    "납입기간",
                    ["10년", "20년", "30년", "전기납"],
                    help="보험료 납입 기간"
                )
        
        with right_col:
            st.markdown("### 📊 미리보기 및 생성")
            
            # 선택된 조건 요약
            selected_conditions = {
                "계약자": {
                    "연령": contractor_age,
                    "국적": contractor_nationality,
                    "직업": contractor_occupation,
                    "월소득": contractor_income
                },
                "피보험자": {
                    "연령": insured_age,
                    "국적": insured_nationality,
                    "직업": insured_occupation
                },
                "상품": {
                    "주계약": product_main,
                    "특약": product_riders
                },
                "계약관계인": {
                    "만기수익자": beneficiary_maturity,
                    "입원상해수익자": beneficiary_hospitalization,
                    "사망시수익자": beneficiary_death,
                    "치매수익자": beneficiary_dementia,
                    "지정대리청구인": proxy_designee
                },
                "계약상태": {
                    "청약방식": application_type,
                    "납입방법": payment_method,
                    "납입기간": payment_period
                }
            }
            
            # 선택된 조건 표시
            total_selections = sum([
                len(contractor_age), len(contractor_nationality), len(contractor_occupation), len(contractor_income),
                len(insured_age), len(insured_nationality), len(insured_occupation),
                len(product_main), len(product_riders),
                sum([beneficiary_maturity, beneficiary_hospitalization, beneficiary_death, beneficiary_dementia, proxy_designee]),
                len(application_type), len(payment_method), len(payment_period)
            ])
            
            if total_selections > 0:
                st.success(f"✅ 총 **{total_selections}개** 조건 선택됨")
                
                # 선택된 조건 상세 표시
                with st.expander("📝 선택된 조건 상세보기", expanded=False):
                    for category, conditions in selected_conditions.items():
                        st.markdown(f"**{category}**")
                        for key, value in conditions.items():
                            if isinstance(value, list) and len(value) > 0:
                                st.write(f"  - {key}: {', '.join(value)}")
                            elif isinstance(value, bool) and value:
                                st.write(f"  - {key}: 지정")
            else:
                st.info("💡 좌측에서 적용할 비즈니스 조건을 선택하세요")
            
            # N x M 조합 설명
            if total_selections > 0:
                st.markdown("""
                > **💡 조합 방식 안내**  
                > 여러 값을 선택하면 **N × M 조합**으로 테스트 케이스가 확장됩니다.  
                > 예: 계약자 연령 2개 × 청약방식 3개 = 6가지 조합 생성
                """)
            
            st.markdown("---")
            
            # 기준 테스트 케이스 선택 (히스토리 우선)
            st.markdown("**📋 기준 테스트 케이스 선택**")
            
            # 히스토리 로드
            history_df = load_history()
            
            if len(history_df) > 0:
                # 히스토리에서 선택 (기본)
                selected_history = st.selectbox(
                    "히스토리에서 선택",
                    range(len(history_df)),
                    format_func=lambda x: f"{history_df.iloc[x]['Timestamp']} | {history_df.iloc[x]['ImageName']} ({history_df.iloc[x]['ScenarioCount']}개)"
                )
                base_scenarios = json.loads(history_df.iloc[selected_history]['Scenarios'])
                base_df = pd.DataFrame(base_scenarios)
                st.info(f"📋 선택된 히스토리: **{len(base_df)}개** 테스트 케이스")
            elif 'df_result' in st.session_state and st.session_state['df_result'] is not None:
                # 히스토리 없으면 현재 결과 사용
                base_df = st.session_state['df_result']
                st.info(f"📋 현재 결과 사용: **{len(base_df)}개** 테스트 케이스")
            else:
                st.warning("⚠️ 먼저 테스트 케이스를 생성하거나 히스토리를 확인하세요")
                base_df = None
            
            st.markdown("---")
            
            # 생성 버튼 (조건 선택 없이도 가능)
            if base_df is not None:
                col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
                with col_btn2:
                    # 버튼 라벨 동적 변경
                    if total_selections > 0:
                        btn_label = "🚀 확장 테스트 케이스 생성"
                        btn_help = "선택한 조건을 반영하여 테스트 케이스를 확장합니다"
                    else:
                        btn_label = "🔍 2차 검수 - 다른 시각으로 보완"
                        btn_help = "기존 테스트 케이스를 다른 시각으로 검토하여 보완합니다"
                    
                    if st.button(btn_label, use_container_width=True, type="primary", help=btn_help):
                        # 조건 텍스트 생성
                        condition_text = ""
                        for category, conditions in selected_conditions.items():
                            condition_lines = []
                            for key, value in conditions.items():
                                if isinstance(value, list) and len(value) > 0:
                                    condition_lines.append(f"  - {key}: {', '.join(value)}")
                                elif isinstance(value, bool) and value:
                                    condition_lines.append(f"  - {key}: 지정")
                            if condition_lines:
                                condition_text += f"\n{category}:\n" + "\n".join(condition_lines)
                        
                        # LLM 프롬프트 생성 (조건 유무에 따라 다른 프롬프트)
                        if total_selections > 0:
                            # 조건 선택됨 → 조건 기반 확장
                            expansion_prompt = f"""
당신은 2차 QA 검수자입니다. 기존 테스트 케이스에 비즈니스 조건을 적용하여 확장합니다.

**선택된 비즈니스 조건:**
{condition_text}

**기존 테스트 케이스 (샘플):**
{base_df.to_dict('records')[:5]}

**중요 규칙:**
1. 기존 테스트 케이스의 화면과 Description을 기준으로 판단하세요.
2. **화면/Description에 해당 조건이 적용될 수 없는 경우, 해당 조건으로 테스트 케이스를 확장하지 마세요.**
3. 예: 로그인 화면에 '계약자 연령' 조건은 적용되지 않음 → 생성 안함
4. 조건이 적용 가능한 경우에만 N × M 조합으로 테스트 케이스를 생성하세요.
5. 실무에서 발생 가능한 시나리오만 생성하세요.
6. 기존 테스트 케이스와 동일한 JSON 구조를 유지하세요.
"""
                        else:
                            # 조건 없음 → 다른 시각으로 검토/보완
                            expansion_prompt = f"""
당신은 2차 QA 검수자입니다. 기존 테스트 케이스를 **다른 시각으로 검토**하여 누락된 케이스를 보완합니다.

**기존 테스트 케이스 (샘플):**
{base_df.to_dict('records')[:5]}

**검토 관점:**
1. **경계값 분석**: 기존 케이스에서 놓친 경계값(최대/최소/경계) 테스트가 있는가?
2. **예외 케이스**: 에러 처리, 타임아웃, 네트워크 오류 등 예외 상황 테스트가 충분한가?
3. **사용자 시나리오**: 실제 사용자가 수행할 다양한 흐름이 커버되었는가?
4. **보안 관점**: 권한 검증, 입력값 검증 등 보안 관련 테스트가 있는가?
5. **비즈니스 규칙**: 도메인 특화 규칙(보험/금융 등)이 테스트되었는가?

**규칙:**
1. 기존 테스트 케이스와 **중복되지 않는** 새로운 관점의 케이스만 생성하세요.
2. 기존 테스트 케이스와 동일한 JSON 구조를 유지하세요.
3. 최소 10개 이상의 보완 테스트 케이스를 생성하세요.
"""
                        
                        with st.spinner("🔍 확장 테스트 케이스 생성 중..."):
                            try:
                                # API 키 검증
                                if not api_key:
                                    st.error("❌ 사이드바에서 API 키를 먼저 입력해주세요!")
                                    st.stop()
                                
                                # API 설정
                                genai.configure(api_key=api_key)
                                
                                # API 호출
                                model = genai.GenerativeModel(
                                    model_name=model_name,
                                    generation_config={"temperature": 0.7},
                                    system_instruction=SYSTEM_PROMPT + "\n\n" + expansion_prompt
                                )
                                
                                response = model.generate_content("위 지침에 따라 테스트 케이스를 생성하세요.")
                                response_text = response.text
                                
                                # JSON 파싱
                                expanded_scenarios = parse_json_response(response_text)
                                expanded_df = pd.DataFrame(expanded_scenarios)
                                
                                # 결과 저장
                                st.session_state['expanded_df'] = expanded_df
                                st.success(f"✅ **{len(expanded_df)}개**의 확장 테스트 케이스가 생성되었습니다!")
                                st.balloons()
                                
                            except Exception as e:
                                st.error(f"❌ 생성 실패: {str(e)}")
            
            # 결과 표시
            if 'expanded_df' in st.session_state and st.session_state['expanded_df'] is not None:
                st.markdown("---")
                st.markdown("### 📊 확장된 테스트 케이스")
                
                expanded_df = st.session_state['expanded_df']
                st.dataframe(expanded_df, use_container_width=True, height=400)
                
                # 버튼 영역 - 3개 버튼
                st.markdown("---")
                col_action1, col_action2, col_action3 = st.columns(3)
                
                with col_action1:
                    # 다운로드 버튼
                    excel_file = create_excel_file(expanded_df)
                    st.download_button(
                        label=f"📥 다운로드 ({len(expanded_df)}개)",
                        data=excel_file,
                        file_name=f"확장_테스트케이스_{time.strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                
                with col_action2:
                    # 히스토리 저장 버튼 (v2)
                    if st.button("💾 히스토리 저장 (v2)", use_container_width=True, type="secondary"):
                        # 원본 히스토리 ID (있으면)
                        parent_id = ""
                        if len(history_df) > 0:
                            parent_id = f"{history_df.iloc[selected_history]['Timestamp']}"
                        
                        # 히스토리에 저장
                        scenarios_list = expanded_df.to_dict('records')
                        if save_to_history(
                            model_name=model_name,
                            image_name="2차 검수 확장",
                            scenarios=scenarios_list,
                            version="v2",
                            parent_id=parent_id
                        ):
                            st.success("✅ 2차 검수 결과가 히스토리(v2)에 저장되었습니다!")
                            st.rerun()
                
                with col_action3:
                    # 병합 버튼 (1차 + 2차 → Final)
                    if st.button("🔗 1차 + 2차 병합 (Final)", use_container_width=True, type="primary"):
                        try:
                            # 원본(base_df)과 확장(expanded_df) 병합
                            merged_df = pd.concat([base_df, expanded_df], ignore_index=True)
                            
                            # 중복 제거 (시나리오ID 기준)
                            if '시나리오ID' in merged_df.columns:
                                merged_df = merged_df.drop_duplicates(subset=['시나리오ID'], keep='first')
                            elif 'TC_ID' in merged_df.columns:
                                merged_df = merged_df.drop_duplicates(subset=['TC_ID'], keep='first')
                            
                            # 세션에 저장
                            st.session_state['merged_df'] = merged_df
                            
                            # 히스토리에 저장
                            parent_id = ""
                            if len(history_df) > 0:
                                parent_id = f"{history_df.iloc[selected_history]['Timestamp']}"
                            
                            scenarios_list = merged_df.to_dict('records')
                            if save_to_history(
                                model_name=model_name,
                                image_name="최종본 (1차+2차 병합)",
                                scenarios=scenarios_list,
                                version="Final",
                                parent_id=parent_id
                            ):
                                st.success(f"✅ **최종본(Final)**: {len(merged_df)}개 테스트 케이스가 저장되었습니다!")
                                st.balloons()
                        except Exception as e:
                            st.error(f"❌ 병합 실패: {str(e)}")
                
                # 병합 결과 표시
                if 'merged_df' in st.session_state and st.session_state['merged_df'] is not None:
                    st.markdown("---")
                    st.markdown("### 🎯 최종본 (Final)")
                    merged_df = st.session_state['merged_df']
                    
                    # 통계
                    col_stat1, col_stat2, col_stat3 = st.columns(3)
                    with col_stat1:
                        st.metric("📋 1차 생성", f"{len(base_df)}개")
                    with col_stat2:
                        st.metric("🔍 2차 검수", f"{len(expanded_df)}개")
                    with col_stat3:
                        st.metric("🎯 최종본", f"{len(merged_df)}개")
                    
                    st.dataframe(merged_df, use_container_width=True, height=300)
                    
                    # 최종본 다운로드
                    final_excel = create_excel_file(merged_df)
                    col_final1, col_final2, col_final3 = st.columns([1, 2, 1])
                    with col_final2:
                        st.download_button(
                            label=f"📥 최종본 다운로드 ({len(merged_df)}개)",
                            data=final_excel,
                            file_name=f"최종_테스트케이스_{time.strftime('%Y%m%d_%H%M%S')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            type="primary"
                        )

# ---------- 애플리케이션 진입점 ----------
if __name__ == "__main__":
    main()  # 메인 함수 실행
