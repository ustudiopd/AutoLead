// 메인 애플리케이션 로직

let currentJobId = null;
let currentFilename = null;
let websocket = null;
let allResults = [];
let filteredResults = [];
let currentPage = 0;
const itemsPerPage = 50;

// DOM 요소
const fileInput = document.getElementById('fileInput');
const uploadArea = document.getElementById('uploadArea');
const fileInfo = document.getElementById('fileInfo');
const fileName = document.getElementById('fileName');
const removeFileBtn = document.getElementById('removeFileBtn');
const processBtn = document.getElementById('processBtn');
const progressSection = document.getElementById('progressSection');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const progressDetail = document.getElementById('progressDetail');
const logContainer = document.getElementById('logContainer');
const resultsSection = document.getElementById('resultsSection');
const resultsTableBody = document.getElementById('resultsTableBody');
const searchInput = document.getElementById('searchInput');
const confidenceFilter = document.getElementById('confidenceFilter');
const reviewFilter = document.getElementById('reviewFilter');
const downloadBtn = document.getElementById('downloadBtn');
const statTotal = document.getElementById('statTotal');
const statHigh = document.getElementById('statHigh');
const statMedium = document.getElementById('statMedium');
const statLow = document.getElementById('statLow');
const pagination = document.getElementById('pagination');

// 탭 관련 요소
const tabButtons = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');
const processTab = document.getElementById('processTab');
const searchTab = document.getElementById('searchTab');

// 검색 관련 요소
const companySearchInput = document.getElementById('companySearchInput');
const emailDomainInput = document.getElementById('emailDomainInput');
const searchBtn = document.getElementById('searchBtn');
const searchResultsSection = document.getElementById('searchResultsSection');
const resultLoading = document.getElementById('resultLoading');
const resultContent = document.getElementById('resultContent');

// 탭 전환
tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
        const targetTab = btn.getAttribute('data-tab');
        
        // 모든 탭 버튼 비활성화
        tabButtons.forEach(b => b.classList.remove('active'));
        // 모든 탭 콘텐츠 숨기기
        tabContents.forEach(c => {
            c.classList.remove('active');
            c.style.display = 'none';
        });
        
        // 선택된 탭 활성화
        btn.classList.add('active');
        if (targetTab === 'process') {
            processTab.classList.add('active');
            processTab.style.display = 'block';
        } else if (targetTab === 'search') {
            searchTab.classList.add('active');
            searchTab.style.display = 'block';
        }
    });
});

// DART 검색
searchBtn.addEventListener('click', async () => {
    const companyName = companySearchInput.value.trim();
    const emailDomain = emailDomainInput.value.trim();
    
    if (!companyName) {
        alert('회사명을 입력해주세요.');
        return;
    }
    
    // 검색 시작
    searchBtn.disabled = true;
    searchBtn.textContent = '검색 중...';
    searchResultsSection.style.display = 'block';
    resultLoading.style.display = 'block';
    resultContent.innerHTML = '';
    
    try {
        const params = new URLSearchParams({ company_name: companyName });
        if (emailDomain) {
            params.append('email_domain', emailDomain);
        }
        
        const response = await fetch(`/api/search/company?${params.toString()}`);
        const data = await response.json();
        
        resultLoading.style.display = 'none';
        
        if (data.success && data.data) {
            const company = data.data;
            resultContent.innerHTML = `
                <div class="result-field">
                    <span class="result-label">회사명</span>
                    <span class="result-value">${company.corp_name || '<span class="empty">없음</span>'}</span>
                </div>
                <div class="result-field">
                    <span class="result-label">법인등록번호</span>
                    <span class="result-value">${company.corp_code || '<span class="empty">없음</span>'}</span>
                </div>
                <div class="result-field">
                    <span class="result-label">종목코드</span>
                    <span class="result-value">${company.stock_code || '<span class="empty">없음</span>'}</span>
                </div>
                <div class="result-field">
                    <span class="result-label">주소</span>
                    <span class="result-value">${company.address || '<span class="empty">없음</span>'}</span>
                </div>
                <div class="result-field">
                    <span class="result-label">웹사이트</span>
                    <span class="result-value">${company.website ? `<a href="${company.website}" target="_blank">${company.website}</a>` : '<span class="empty">없음</span>'}</span>
                </div>
                <div class="result-field">
                    <span class="result-label">KSIC 코드</span>
                    <span class="result-value">${company.ksic_code || '<span class="empty">없음</span>'}</span>
                </div>
                <div class="result-field">
                    <span class="result-label">KSIC 업종명</span>
                    <span class="result-value">${company.ksic_name || '<span class="empty">없음</span>'}</span>
                </div>
                <div class="result-field">
                    <span class="result-label">대표이사</span>
                    <span class="result-value">${company.ceo_name || '<span class="empty">없음</span>'}</span>
                </div>
                <div class="result-field">
                    <span class="result-label">설립일</span>
                    <span class="result-value">${company.established_date || '<span class="empty">없음</span>'}</span>
                </div>
                <div class="result-field">
                    <span class="result-label">검색 방법</span>
                    <span class="result-value">${company.search_method || '<span class="empty">없음</span>'}</span>
                </div>
                <div class="result-field">
                    <span class="result-label">매칭 수</span>
                    <span class="result-value">${company.match_count || 0}</span>
                </div>
                ${company.all_matches && company.all_matches.length > 0 ? `
                <div class="result-field">
                    <span class="result-label">모든 매칭</span>
                    <span class="result-value">${company.all_matches.join(', ')}</span>
                </div>
                ` : ''}
            `;
        } else {
            resultContent.innerHTML = `
                <div class="result-error">
                    <p>${data.message || '회사를 찾을 수 없습니다.'}</p>
                </div>
            `;
        }
    } catch (error) {
        resultLoading.style.display = 'none';
        resultContent.innerHTML = `
            <div class="result-error">
                <p>검색 중 오류가 발생했습니다: ${error.message}</p>
            </div>
        `;
    } finally {
        searchBtn.disabled = false;
        searchBtn.textContent = '검색';
    }
});

// Enter 키로 검색
companySearchInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        searchBtn.click();
    }
});

emailDomainInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        searchBtn.click();
    }
});

// 파일 업로드
uploadArea.addEventListener('click', () => fileInput.click());
uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.style.borderColor = '#666';
});
uploadArea.addEventListener('dragleave', () => {
    uploadArea.style.borderColor = '#e0e0e0';
});
uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.style.borderColor = '#e0e0e0';
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFileSelect(files[0]);
    }
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleFileSelect(e.target.files[0]);
    }
});

removeFileBtn.addEventListener('click', () => {
    fileInput.value = '';
    currentFilename = null;
    fileInfo.style.display = 'none';
    processBtn.disabled = true;
});

async function handleFileSelect(file) {
    if (!file.name.endsWith('.csv')) {
        alert('CSV 파일만 업로드 가능합니다.');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error('파일 업로드 실패');
        }

        const data = await response.json();
        currentFilename = data.filename;
        fileName.textContent = file.name;
        fileInfo.style.display = 'flex';
        processBtn.disabled = false;
        addLog('파일 업로드 완료: ' + file.name, 'success');
    } catch (error) {
        addLog('파일 업로드 오류: ' + error.message, 'error');
        alert('파일 업로드에 실패했습니다.');
    }
}

// 처리 시작
processBtn.addEventListener('click', async () => {
    if (!currentFilename) return;

    try {
        const response = await fetch('/api/process', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ filename: currentFilename })
        });

        if (!response.ok) {
            throw new Error('처리 시작 실패');
        }

        const data = await response.json();
        currentJobId = data.job_id;
        
        progressSection.style.display = 'block';
        resultsSection.style.display = 'none';
        processBtn.disabled = true;
        
        updateProgress(0, 100, '처리 시작...');
        addLog('처리가 시작되었습니다.', 'success');
        
        // WebSocket 연결
        connectWebSocket(currentJobId);
        
        // 상태 폴링 시작
        pollJobStatus();
    } catch (error) {
        addLog('처리 시작 오류: ' + error.message, 'error');
        alert('처리 시작에 실패했습니다.');
    }
});

// WebSocket 연결
function connectWebSocket(jobId) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/progress/${jobId}`;
    
    websocket = new WebSocket(wsUrl);
    
    websocket.onmessage = (event) => {
        const progress = JSON.parse(event.data);
        updateProgress(
            progress.current,
            progress.total,
            progress.current_item || progress.message || ''
        );
    };
    
    websocket.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
    
    websocket.onclose = () => {
        console.log('WebSocket closed');
    };
}

// 작업 상태 폴링
async function pollJobStatus() {
    if (!currentJobId) return;

    const interval = setInterval(async () => {
        try {
            const response = await fetch(`/api/status/${currentJobId}`);
            if (!response.ok) return;

            const status = await response.json();
            
            if (status.status === 'completed') {
                clearInterval(interval);
                if (websocket) websocket.close();
                updateProgress(100, 100, '처리 완료');
                addLog('처리가 완료되었습니다.', 'success');
                await loadResults();
            } else if (status.status === 'failed') {
                clearInterval(interval);
                if (websocket) websocket.close();
                addLog('처리 실패: ' + (status.error || '알 수 없는 오류'), 'error');
                processBtn.disabled = false;
            } else if (status.progress) {
                updateProgress(
                    status.progress.current,
                    status.progress.total,
                    status.progress.current_item || ''
                );
            }
        } catch (error) {
            console.error('Status polling error:', error);
        }
    }, 1000);
}

// 진행 상황 업데이트
function updateProgress(current, total, message) {
    const percentage = total > 0 ? (current / total * 100) : 0;
    progressFill.style.width = percentage + '%';
    progressText.textContent = Math.round(percentage) + '%';
    progressDetail.textContent = message || '처리 중...';
    
    if (message && message !== '처리 시작...') {
        addLog(`[${current}/${total}] ${message}`);
    }
}

// 로그 추가
function addLog(message, type = '') {
    const logEntry = document.createElement('div');
    logEntry.className = 'log-entry' + (type ? ' ' + type : '');
    logEntry.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
    logContainer.appendChild(logEntry);
    logContainer.scrollTop = logContainer.scrollHeight;
}

// 결과 로드
async function loadResults() {
    if (!currentJobId) return;

    try {
        let allData = [];
        let skip = 0;
        const limit = 1000;

        // 모든 데이터 가져오기
        while (true) {
            const response = await fetch(`/api/results/${currentJobId}?skip=${skip}&limit=${limit}`);
            if (!response.ok) break;

            const data = await response.json();
            allData = allData.concat(data.rows.map(r => r.data));

            if (data.rows.length < limit) break;
            skip += limit;
        }

        allResults = allData;
        
        // 통계는 첫 번째 응답에서 가져옴
        if (allData.length > 0) {
            const firstResponse = await fetch(`/api/results/${currentJobId}?skip=0&limit=1`);
            if (firstResponse.ok) {
                const firstData = await firstResponse.json();
                updateStatistics(firstData.statistics);
            }
        }
        
        applyFilters();
        resultsSection.style.display = 'block';
    } catch (error) {
        addLog('결과 로드 오류: ' + error.message, 'error');
    }
}

// 통계 업데이트
function updateStatistics(stats) {
    statTotal.textContent = stats.total || 0;
    statHigh.textContent = stats.high || 0;
    statMedium.textContent = stats.medium || 0;
    statLow.textContent = stats.low || 0;
}

// 필터 적용
function applyFilters() {
    const searchTerm = searchInput.value.toLowerCase();
    const confidenceValue = confidenceFilter.value;
    const reviewValue = reviewFilter.value;

    filteredResults = allResults.filter(row => {
        const matchesSearch = !searchTerm || 
            Object.values(row).some(val => 
                String(val).toLowerCase().includes(searchTerm)
            );
        const matchesConfidence = !confidenceValue || 
            row.Confidence_Score === confidenceValue;
        const matchesReview = !reviewValue || 
            row.Review_Status === reviewValue;

        return matchesSearch && matchesConfidence && matchesReview;
    });

    currentPage = 0;
    renderTable();
    renderPagination();
}

searchInput.addEventListener('input', applyFilters);
confidenceFilter.addEventListener('change', applyFilters);
reviewFilter.addEventListener('change', applyFilters);

// 테이블 렌더링
function renderTable() {
    const start = currentPage * itemsPerPage;
    const end = start + itemsPerPage;
    const pageData = filteredResults.slice(start, end);

    resultsTableBody.innerHTML = '';

    pageData.forEach(row => {
        const tr = document.createElement('tr');
        
        const confidenceClass = row.Confidence_Score?.toLowerCase() || '';
        const reviewClass = row.Review_Status === 'Approved' ? 'approved' : 'review';
        
        tr.innerHTML = `
            <td>${escapeHtml(row['Company name'] || '')}</td>
            <td>${escapeHtml(row['Work email'] || '')}</td>
            <td>${escapeHtml(row.DART_Corp_Name || '')}</td>
            <td>${escapeHtml(row.DART_Address || '')}</td>
            <td>${escapeHtml(row.DART_Website || '')}</td>
            <td>${escapeHtml(row.DART_KSIC_Code || '')}</td>
            <td>${escapeHtml(row.SIC_Code || '')}</td>
            <td><span class="badge badge-${confidenceClass}">${escapeHtml(row.Confidence_Score || '')}</span></td>
            <td><span class="badge badge-${reviewClass}">${escapeHtml(row.Review_Status || '')}</span></td>
        `;
        
        resultsTableBody.appendChild(tr);
    });
}

// 페이지네이션 렌더링
function renderPagination() {
    const totalPages = Math.ceil(filteredResults.length / itemsPerPage);
    
    if (totalPages <= 1) {
        pagination.innerHTML = '';
        return;
    }

    let html = '';
    
    // 이전 버튼
    html += `<button ${currentPage === 0 ? 'disabled' : ''} onclick="goToPage(${currentPage - 1})">이전</button>`;
    
    // 페이지 정보
    html += `<span class="page-info">${currentPage + 1} / ${totalPages}</span>`;
    
    // 다음 버튼
    html += `<button ${currentPage >= totalPages - 1 ? 'disabled' : ''} onclick="goToPage(${currentPage + 1})">다음</button>`;
    
    pagination.innerHTML = html;
}

function goToPage(page) {
    const totalPages = Math.ceil(filteredResults.length / itemsPerPage);
    if (page >= 0 && page < totalPages) {
        currentPage = page;
        renderTable();
        renderPagination();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

// 다운로드
downloadBtn.addEventListener('click', () => {
    if (!currentJobId) return;
    window.location.href = `/api/results/${currentJobId}/download`;
});

// 유틸리티
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
