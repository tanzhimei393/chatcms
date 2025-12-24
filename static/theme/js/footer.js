// 初始化页脚订阅表单
async function initializeFooterSubscribe() {
    const form = document.getElementById('footer-subscribe-form');
    const fingerprintInput = document.getElementById('footer-browser-fingerprint');
    
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
        
        const emailInput = document.getElementById('footer-subscribe-email');
        const email = emailInput.value.trim();
        
        if (!email || !email.includes('@')) {
            alert('请输入有效的邮箱地址');
            return;
        }
        
        const submitBtn = form.querySelector('button[type="submit"]');
        const originalHtml = submitBtn.innerHTML;
        
        // 显示加载状态
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
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
            submitBtn.innerHTML = originalHtml;
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

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    initializeFooterSubscribe();
});