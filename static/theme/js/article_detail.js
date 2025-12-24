// 页面加载时初始化
document.addEventListener('DOMContentLoaded', () => {
    setupBackToTopFunctionality();
    setupFavoriteFunctionality();
    setupCopyLinkFunctionality();
    setupSubscribeFunctionality();
});

// 设置返回顶部按钮
function setupBackToTopFunctionality() {
    const backToTopButton = document.getElementById('back-to-top');
    if (backToTopButton) {
        window.addEventListener('scroll', () => {
            if (window.pageYOffset > 300) {
                backToTopButton.classList.remove('opacity-0', 'invisible');
                backToTopButton.classList.add('opacity-100', 'visible');
            } else {
                backToTopButton.classList.remove('opacity-100', 'visible');
                backToTopButton.classList.add('opacity-0', 'invisible');
            }
        });

        backToTopButton.addEventListener('click', () => {
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        });
    }
}

// 收藏按钮交互
function setupFavoriteFunctionality(){
    const favoriteBtn = document.getElementById('favorite-btn');
    if (favoriteBtn) {
        favoriteBtn.addEventListener('click', function() {
            const icon = this.querySelector('i');
            const text = this.querySelector('span');

            if (icon.classList.contains('far')) {
                // 变为已收藏状态
                icon.classList.remove('far');
                icon.classList.add('fas');
                text.textContent = '已收藏';
                this.classList.add('text-primary');

                // 显示收藏成功提示
                const notification = document.createElement('div');
                notification.className = 'fixed bottom-6 left-1/2 transform -translate-x-1/2 bg-green-500 text-white px-4 py-2 rounded-md shadow-lg z-50 transition-opacity duration-300';
                notification.textContent = '收藏成功！';
                document.body.appendChild(notification);

                setTimeout(() => {
                    notification.style.opacity = '0';
                    setTimeout(() => {
                        document.body.removeChild(notification);
                    }, 300);
                }, 2000);
            } else {
                // 变为未收藏状态
                icon.classList.remove('fas');
                icon.classList.add('far');
                text.textContent = '收藏文章';
                this.classList.remove('text-primary');
            }
        });
    }
}

// 复制链接功能
function setupCopyLinkFunctionality(){
    const copyLinkBtn = document.querySelector('.fa-link').parentElement;
    if (copyLinkBtn) {
        copyLinkBtn.addEventListener('click', function() {
            // 创建临时输入框
            const tempInput = document.createElement('input');
            document.body.appendChild(tempInput);
            tempInput.value = window.location.href;
            tempInput.select();
            document.execCommand('copy');
            document.body.removeChild(tempInput);

            // 显示复制成功提示
            const notification = document.createElement('div');
            notification.className = 'fixed bottom-6 left-1/2 transform -translate-x-1/2 bg-green-500 text-white px-4 py-2 rounded-md shadow-lg z-50 transition-opacity duration-300';
            notification.textContent = '链接已复制！';
            document.body.appendChild(notification);

            setTimeout(() => {
                notification.style.opacity = '0';
                setTimeout(() => {
                    document.body.removeChild(notification);
                }, 300);
            }, 2000);
        });
    }
}

// 初始化页脚订阅表单
async function setupSubscribeFunctionality() {
    const form = document.getElementById('subscribe-form');
    const fingerprintInput = document.getElementById('browser-fingerprint');
    
    if (!form || !fingerprintInput) return;
    
    // 生成浏览器指纹
    try {
        const fp = await fpPromise;
        const result = await fp.get();
        fingerprintInput.value = result.visitorId;
    } catch (error) {
        fingerprintInput.value = await generateSimpleFingerprint();
    }
    
    // 处理表单提交
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const emailInput = document.getElementById('subscribe-email');
        const email = emailInput.value.trim();
        
        if (!email || !email.includes('@')) {
            alert('请输入有效的邮箱地址');
            return;
        }
        
        const submitBtn = form.querySelector('button[type="submit"]');
        const originalText = submitBtn.textContent;
        
        // 显示订阅状态
        submitBtn.textContent = '订阅中...';
        submitBtn.disabled = true;
        
        try {
            const formData = new FormData(form);
            const response = await fetch('/subscribe', {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            alert(result.message);
            
            if (result.success) {
                emailInput.value = '';
            }
        } catch (error) {
            alert('订阅失败，请稍后重试');
        } finally {
            submitBtn.textContent = originalText;
            submitBtn.disabled = false;
        }
    });
}

// 备用简单指纹生成
async function generateSimpleFingerprint() {
    const components = [
        navigator.userAgent,
        `${screen.width}x${screen.height}`,
        screen.colorDepth,
        new Date().getTimezoneOffset(),
        navigator.language
    ].join('|');
    
    try {
        const encoder = new TextEncoder();
        const data = encoder.encode(components);
        const hashBuffer = await crypto.subtle.digest('SHA-256', data);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    } catch (e) {
        let hash = 0;
        for (let i = 0; i < components.length; i++) {
            hash = ((hash << 5) - hash) + components.charCodeAt(i);
            hash |= 0;
        }
        return hash.toString(16);
    }
}