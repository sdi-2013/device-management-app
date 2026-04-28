import streamlit as st
import qrcode
import pandas as pd
from io import BytesIO
from modules.services import AssetService, ProcessService

def render_qr_gen():
    st.title("🖼️ QR 코드 생성기")
    
    # 1. Select Asset
    assets = AssetService.get_all_assets()
    if assets.empty:
        st.info("등록된 장비가 없습니다.")
        return

    # Dynamic Type Filter
    all_types = sorted(assets['type'].unique().tolist())
    # Add 'Entire' option
    type_options = ["전체"] + all_types
    
    st.markdown("### 🔍 장비 필터")
    selected_type = st.radio("단말기 종류 선택", type_options, horizontal=True)
    
    if selected_type != "전체":
        assets = assets[assets['type'] == selected_type].copy()
        if assets.empty:
            st.warning("선택한 종류의 장비가 없습니다.")
            return

    # Helper for label
    assets['label'] = assets.apply(lambda x: f"[{x['id']}] {x['model']} ({x['type']})", axis=1)
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("장비 선택")
        options = assets['label'].tolist()
        sel = st.selectbox("QR 코드를 생성할 장비를 선택하세요", options)
        
        target_id = sel.split(']')[0].replace('[', '')
        asset_info = assets[assets['id'] == target_id].iloc[0]
        
        # Generate QR
        qr = qrcode.make(target_id)
        buf = BytesIO()
        qr.save(buf, format="PNG")
        img_bytes = buf.getvalue()
        
        st.image(img_bytes, caption=f"QR Code for {target_id}", width=200)
        
        st.download_button(
            label="💾 QR 이미지 다운로드",
            data=img_bytes,
            file_name=f"QR_{target_id}.png",
            mime="image/png",
            type="primary"
        )

    with col2:
        st.subheader("장비 상세 정보")
        
        # Find process info if deployed
        procs = ProcessService.get_all_processes({'asset_id': target_id})
        
        info_lines = []
        info_lines.append(f"<p><strong>관리번호:</strong> <span style='font-size: 1.2em; color: #4CAF50;'>{asset_info['id']}</span></p>")
        info_lines.append(f"<p><strong>모델명:</strong> {asset_info['model']}</p>")
        info_lines.append(f"<p><strong>제조사:</strong> {asset_info['maker']}</p>")
        
        if not procs.empty:
            p = procs.iloc[0]
            info_lines.append(f"<hr>")
            info_lines.append(f"<p><strong>공장:</strong> {p['factory']}</p>")
            info_lines.append(f"<p><strong>공정:</strong> {p['name']}</p>")
            info_lines.append(f"<p><strong>호기:</strong> {p['hogi']}</p>")
            info_lines.append(f"<p><strong>IP:</strong> {p['ip']}</p>")
            st.success("✅ 공정 배치됨")
        else:
            # Fallback: Check if asset has location string (Legacy/Manual)
            if asset_info['status'] == '투입중' and asset_info['location']:
                # Parse location string if possible? Or just display
                info_lines.append(f"<hr>")
                info_lines.append(f"<p><strong>위치 정보:</strong> {asset_info['location']}</p>")
                st.success("✅ 배치됨") # Unified status
            elif asset_info['status'] == '투입중':
                 st.warning("⚠️ 투입중이나 위치 정보 없음")
            else:
                 st.info(f"ℹ️ {asset_info['status']}")

        st.markdown(f"""
        <style>
        .qr-asset-detail {{
            background-color: var(--secondary-background-color);
            padding: 20px;
            border-radius: 10px;
            border: 1px solid var(--text-color-alpha-20);
            color: var(--text-color);
        }}
        </style>
        <div class="qr-asset-detail">
            {''.join(info_lines)}
        </div>
        """, unsafe_allow_html=True)

