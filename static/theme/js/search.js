// 页面加载时初始化渲染
document.addEventListener('DOMContentLoaded', () => {
    setupBackToTopFunctionality();
    setupSearchFunctionality();
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

// 设置搜索功能
function setupSearchFunctionality() {
    const searchInput = document.getElementById('article-search');
    const searchButton = document.getElementById('search-button');
    const orderBySelect = document.getElementById('article-order-by');

    const performSearch = () => {
        const searchTerm = searchInput.value.trim();
        const orderByValue = orderBySelect.value.trim();
        if (searchTerm) {
            window.location.href = `/search?keyword=${searchTerm}&order_by=${orderByValue}`;
        } else {
            window.location.href = `/search?keyword=&order_by=${orderByValue}`;
        }
    };

    searchButton.addEventListener('click', performSearch);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            performSearch();
        }
    });
}