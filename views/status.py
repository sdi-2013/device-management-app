import streamlit as st
import pandas as pd
from modules.services import AssetService

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

def render_status():
    st.title("📊 투입 현황")
    
    # Get Data
    assets = AssetService.get_all_assets()
    
    if assets.empty:
        st.info("데이터가 없습니다.")
        return

    # Metrics
    total = len(assets)
    deployed = len(assets[assets['status'] == '투입중'])
    waiting = len(assets[assets['status'] == '대기중'])
    repair = len(assets[assets['status'] == '수리중'])
    disposal = len(assets[assets['status'] == '폐기예정'])
    
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("총 자산", f"{total}대")
    c2.metric("투입중", f"{deployed}대", delta=f"{deployed/total*100:.1f}%")
    c3.metric("대기중", f"{waiting}대")
    c4.metric("수리중", f"{repair}대")
    c5.metric("폐기예정", f"{disposal}대")
    
    st.markdown("---")
    
    # Deployed List
    st.subheader("🚀 현재 투입된 장비 목록")
    
    # Use ProcessService to get detailed location
    from modules.services import ProcessService
    
    deployed_assets = assets[assets['status'] == '투입중'].copy()
    
    if not deployed_assets.empty:
        # Get Process Info
        procs = ProcessService.get_all_processes()
        # Merge: deployed_assets (id) <-> procs (asset_id)
        # We want to keep all deployed assets.
        merged = pd.merge(deployed_assets, procs, left_on='id', right_on='asset_id', how='left', suffixes=('', '_proc'))
        
        # Prepare Display Columns
        # Target: ID(자체관리번호), Type(단말기종류), Model(모델명), OS, IP, Dept(부서), Factory(공장), Name(공정), Hogi(호기), DeployDate(투입일자)
        
        # Handling NaN for Manual Location assets (not in process master)
        # If merged 'ip' is NaN, it means not in process master.
        # We could parse 'location' string if needed, but User asked to split "Like Process Master".
        # So fields will be empty if not in Process Master.
        
        # Create final DF
        final_df = merged.copy()
        
        # Rename/Select columns
        # assets: id, type, model, os, deploy_date
        # processes: ip, dept, factory, name, hogi
        
        # 1. Filters
        # 1. Filters
        st.markdown("##### 🔍 조건 검색 (다중 선택 가능 - 우선순위 적용)")
        
        # Layout: 4 columns (Dept -> Factory -> Type -> OS)
        f_c1, f_c2, f_c3, f_c4 = st.columns(4)
        
        # --- Cascade Logic ---
        # 1. Dept (Priority 1)
        depts_opts = sorted([x for x in final_df['dept'].unique() if pd.notna(x) and x])
        sel_depts = f_c1.multiselect("부서", depts_opts, placeholder="전체", key="status_f_dept")
        
        # Filter for Step 2
        step1_df = final_df.copy()
        if sel_depts:
            step1_df = step1_df[step1_df['dept'].isin(sel_depts)]
            
        # 2. Factory (Priority 2) - Options derived from Step 1
        factories_opts = sorted([x for x in step1_df['factory'].unique() if pd.notna(x) and x])
        
        # Validate Selection (Prevent Streamlit Error)
        if "status_f_factory" in st.session_state:
            st.session_state["status_f_factory"] = [x for x in st.session_state["status_f_factory"] if x in factories_opts]
            
        sel_factories = f_c2.multiselect("공장", factories_opts, placeholder="전체", key="status_f_factory")
        
        # Filter for Step 3
        step2_df = step1_df.copy()
        if sel_factories:
            step2_df = step2_df[step2_df['factory'].isin(sel_factories)]
            
        # 3. Type (Priority 3) - Options derived from Step 2
        types_opts = sorted([x for x in step2_df['type'].unique() if pd.notna(x) and x])
        
        if "status_f_type" in st.session_state:
            st.session_state["status_f_type"] = [x for x in st.session_state["status_f_type"] if x in types_opts]
            
        sel_types = f_c3.multiselect("단말기종류", types_opts, placeholder="전체", key="status_f_type")
        
        # Filter for Step 4
        step3_df = step2_df.copy()
        if sel_types:
            step3_df = step3_df[step3_df['type'].isin(sel_types)]
            
        # 4. OS (Priority 4) - Options derived from Step 3
        oss_opts = sorted([x for x in step3_df['os'].unique() if pd.notna(x) and x])
        
        if "status_f_os" in st.session_state:
            st.session_state["status_f_os"] = [x for x in st.session_state["status_f_os"] if x in oss_opts]
            
        sel_oss = f_c4.multiselect("OS", oss_opts, placeholder="전체", key="status_f_os")
        
        # Final Filter
        if sel_oss:
            final_df = step3_df[step3_df['os'].isin(sel_oss)]
        else:
            final_df = step3_df
        
        # Select & Rename
        # Capture filtered data for charts before renaming columns
        chart_source = final_df.copy()
        
        # Select & Rename
        display_cols = {
            "id": "자체관리번호",
            "type": "단말기종류",
            "model": "모델명",
            "os": "OS",
            "ip": "IP",
            "dept": "부서",
            "factory": "공장",
            "name": "공정",
            "hogi": "호기",
            "deploy_date": "투입일자"
        }
        
        # Ensure columns exist (if join failed or empty)
        for c in ["ip", "dept", "factory", "name", "hogi"]:
            if c not in final_df.columns: final_df[c] = ""
            
        final_view = final_df[list(display_cols.keys())].rename(columns=display_cols)
        
        # Show count
        st.markdown(f"**조회 결과: {len(final_view)}건**")
        
        st.dataframe(final_view, use_container_width=True, hide_index=True)
    else:
        st.info("투입된 장비가 없습니다.")
        # Empty source for charts if no data
        chart_source = pd.DataFrame(columns=['type', 'model', 'os'])
    
    # Charts - 3D Pie Charts (Now Dynamic based on Filter)
    st.subheader("📈 장비 분포 현황 (조회 결과 기준)")
    
    if not PLOTLY_AVAILABLE:
        st.warning("⚠️ Plotly 라이브러리가 설치되지 않았습니다. `pip install plotly` 명령으로 설치해주세요.")
        # Fallback to simple bar chart
        if not chart_source.empty:
             st.bar_chart(chart_source['type'].value_counts())
        return
    
    if chart_source.empty:
        st.info("차트를 표시할 데이터가 없습니다.")
        return

    # Create 3 columns for the charts
    chart_col1, chart_col2, chart_col3 = st.columns(3)
    
    # Chart 1: MES 단말기 모델별 분포
    with chart_col1:
        st.markdown("##### 🖥️ MES 단말기 모델 현황")
        mes_deployed = chart_source[chart_source['type'] == 'MES단말기']
        
        if not mes_deployed.empty:
            mes_model_counts = mes_deployed['model'].value_counts().reset_index()
            mes_model_counts.columns = ['모델명', '수량']
            
            fig1 = px.pie(mes_model_counts, values='수량', names='모델명',
                         hole=0.4,
                         color_discrete_sequence=px.colors.qualitative.Set3)
            fig1.update_traces(textposition='inside', textinfo='percent+label',
                              marker=dict(line=dict(color='#000000', width=1)))
            fig1.update_layout(showlegend=False, height=300, margin=dict(t=30, b=0, l=0, r=0))
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.info("조회된 MES 단말기가 없습니다.")
    
    # Chart 2: MES OS 분포
    with chart_col2:
        st.markdown("##### 💿 MES OS 현황")
        mes_os_data = chart_source[chart_source['type'] == 'MES단말기']
        
        if not mes_os_data.empty:
            mes_os_counts = mes_os_data['os'].value_counts().reset_index()
            mes_os_counts.columns = ['OS', '수량']
            
            fig2 = px.pie(mes_os_counts, values='수량', names='OS',
                          hole=0.4,
                          color_discrete_sequence=px.colors.qualitative.Bold)
            fig2.update_traces(textposition='inside', textinfo='percent+label',
                              marker=dict(line=dict(color='#000000', width=1)))
            fig2.update_layout(showlegend=False, height=300, margin=dict(t=30, b=0, l=0, r=0))
            st.plotly_chart(fig2, use_container_width=True)
        else:
             st.info("조회된 MES 단말기가 없습니다.")

    # Chart 3: 라벨프린터 모델별 분포
    with chart_col3:
        st.markdown("##### 🖨️ 라벨프린터 모델 현황")
        printer_deployed = chart_source[chart_source['type'] == '라벨프린터']
        
        if not printer_deployed.empty:
            printer_model_counts = printer_deployed['model'].value_counts().reset_index()
            printer_model_counts.columns = ['모델명', '수량']
            
            fig3 = px.pie(printer_model_counts, values='수량', names='모델명',
                         hole=0.4,
                         color_discrete_sequence=px.colors.qualitative.Pastel)
            fig3.update_traces(textposition='inside', textinfo='percent+label',
                              marker=dict(line=dict(color='#000000', width=1)))
            fig3.update_layout(showlegend=False, height=300, margin=dict(t=30, b=0, l=0, r=0))
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("조회된 라벨프린터가 없습니다.")
