// 页面加载时初始化渲染
document.addEventListener('DOMContentLoaded', () => {
    initNavbar();
    initMobileMenu();
});

// 导航栏滚动效果
function initNavbar() {
    const navbar = document.getElementById('navbar');
    window.addEventListener('scroll', () => {
        if (window.scrollY > 50) {
            navbar.classList.add('shadow-md');
            navbar.classList.remove('bg-white/90');
            navbar.classList.add('bg-white');
        } else {
            navbar.classList.remove('shadow-md');
            navbar.classList.add('bg-white/90');
            navbar.classList.remove('bg-white');
        }
    });
}

// 移动端菜单切换
function initMobileMenu() {
    const menuToggle = document.getElementById('menu-toggle');
    const mobileMenu = document.getElementById('mobile-menu');

    // 切换菜单显示状态
    const toggleMenu = () => {
        mobileMenu.classList.toggle('hidden');
    };

    menuToggle.addEventListener('click', toggleMenu);

    // 点击非菜单区域关闭菜单
    document.addEventListener('click', (e) => {
        // 检查是否是移动设备
        if (window.innerWidth < 768) {
            // 检查点击是否不在菜单内且不在菜单按钮内
            if (!mobileMenu.contains(e.target) && !menuToggle.contains(e.target)) {
                mobileMenu.classList.add('hidden');
            }
        }
    });

    // 防止菜单内部点击事件冒泡导致菜单关闭
    mobileMenu.addEventListener('click', (e) => {
        e.stopPropagation();
    });
}