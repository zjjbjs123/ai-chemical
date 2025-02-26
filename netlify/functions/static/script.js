console.log('script.js 文件已加载');

function downloadAttachment(filePath) {
    window.open(`/download_attachment/${filePath}`, '_blank');
}
function runExecutable(menuId) {
    // 这里调用运行可执行程序的接口
    fetch(`/run_executable?menu_id=${menuId}`)
      .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.text();
        })
      .then(data => {
            // 这里可以根据返回的数据做进一步处理，例如提示用户打开协议
            console.log('运行可执行程序的返回数据:', data);
            if (data.startsWith('myapp://')) {
                // 示例处理，可根据实际情况修改
                Swal.fire({
                    icon: 'info',
                    title: '启动程序',
                    text: `即将通过自定义协议启动程序：${data}`
                }).then(() => {
                    window.location.href = data;
                });
            }
        })
      .catch(error => {
            console.error('运行可执行程序时出错:', error);
            Swal.fire({
                icon: 'error',
                title: '请求出错',
                text: '运行可执行程序时发生错误，请稍后重试。'
            });
        });
}