# Wechu

## 서버 실행

### Backend 실행
```bash
cd fastapi-test

# 가상환경 활성화
.venv\Scripts\activate

# 서버 실행
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

### Frontend 실행
```bash
# 프로젝트 루트에서
npm run dev
```
---

## 작업 프로세스

```bash
# 📥 작업 시작
git checkout develop
git checkout -b feature/작업명

# 💾 작업 완료
git add .
git commit -m "feat: [카테고리] 작업 내용"
git push origin feature/작업명
# → GitHub에서 PR 생성 (develop으로!)

# 🔄 Merge 후
# 1. GitHub에서 Delete branch
# 2. 로컬 정리
git checkout develop
git branch -D feature/작업명

# 📥 다음 작업 전
# 1. GitHub에서 Sync fork → Update branch
# 2. 로컬에서 pull
git checkout develop
git pull origin develop
```

---

## ⚠️ 주의사항

- ❌ **main 브랜치로 PR 금지** → ✅ 항상 `develop`으로
- ❌ **develop에 직접 commit/push 금지** → ✅ `feature/` 브랜치 사용
- ✅ **Merge 후 브랜치 삭제 필수**
- ✅ **다음 작업 전 Fork Sync 필수**

---

## 🤝 협업 가이드

### 📋 작업 프로세스 (전체 흐름)

```
1. Fork & Clone
   ↓
2. 이슈 생성
   ↓
3. Feature 브랜치 작업
   ↓
4. Push & PR 생성
   ↓
5. 라벨/담당자 설정 & 이슈 연결
   ↓
6. Merge & 브랜치 삭제
   ↓
7. 로컬 동기화 (다음 작업 시)
```

---

### 1️⃣ Fork 및 Clone (최초 1회)

#### GitHub에서 Fork 생성
1. 저장소 우측 상단 `Fork` 버튼 클릭
2. ⚠️ **중요**: `Copy the main branch only` 체크 **해제** (모든 브랜치 포함)
3. `Create fork` 클릭

#### 로컬로 Clone
```bash
git clone https://github.com/본인아이디/Wechu.git
cd Wechu
```

---

### 2️⃣ 이슈 생성

1. **원본 저장소** (munwalk/Wechu)에서 `Issues` 탭 이동
2. `New issue` 클릭
3. 제목과 내용 작성

---

### 3️⃣ Feature 브랜치 작업

```bash
# develop 브랜치에서 feature 브랜치 생성
git checkout develop
git checkout -b feature/작업명

# 예시:
# git checkout -b feature/chatbot
```

#### 코드 작업 후 커밋
```bash
git add .
git commit -m "feat: [카테고리] 작업 내용"
git push origin feature/작업명
```

---

### 4️⃣ Pull Request 생성

1. GitHub의 **본인 Fork 저장소** 접속
2. `Compare & pull request` 버튼 클릭
3. **Base repository** 설정:
   - `base repository`: `munwalk/Wechu`
   - `base`: `develop` ⚠️ **main이 아님!**
   - `compare`: `feature/작업명`

---

### 5️⃣ PR 설정

#### 우측 사이드바 설정
- **Assignees**: 본인 지정
- **Labels**: 작업 성격 선택 (`feat`, `fix`, `docs` 등)
- **Development**: `Closes #이슈번호` 입력하여 이슈 연결

#### Create pull request 클릭

---

### 6️⃣ Merge 후 정리

#### PR이 Merge 되면:

1. **GitHub에서 브랜치 삭제**
   - PR 페이지에서 `Delete branch` 버튼 클릭

2. **로컬에서 정리**
   ```bash
   git checkout develop
   git branch -D feature/작업명
   ```

---

### 7️⃣ 다음 작업 전 동기화

⚠️ **다른 팀원의 작업이 Merge된 후, 다음 작업 전에만 실행**

#### GitHub에서 Sync (추천 ✅)
1. **본인 Fork 저장소** 접속
2. develop 브랜치 선택
3. `Sync fork` 버튼 클릭
4. `Update branch` 클릭

#### 로컬에서 Pull
```bash
git checkout develop
git pull origin develop
```
