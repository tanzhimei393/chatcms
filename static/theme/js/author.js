// 页面加载时初始化渲染
document.addEventListener('DOMContentLoaded', () => {
    setupBackToTopFunctionality();
    setupApplyBtnFunctionality();
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

//申请成为作者
function setupApplyBtnFunctionality(){
    document.getElementById('applyBtn').addEventListener('click', function() {
        document.getElementById('messageBox').classList.remove('hidden');
        document.getElementById('messageBox').classList.add('fade-in');
    });

    document.getElementById('closeBtn').addEventListener('click', function() {
        document.getElementById('messageBox').classList.add('hidden');
    });

    // 点击消息框外部区域关闭
    document.getElementById('messageBox').addEventListener('click', function(e) {
        if (e.target === this) {
            this.classList.add('hidden');
        }
    });
}