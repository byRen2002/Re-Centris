package utils

import (
    "bytes"
    "crypto/sha256"
    "encoding/hex"
    "fmt"
    "math"
    "sort"
)

// TLSH (Trend Micro Locality Sensitive Hash) 是一种局部敏感哈希算法
// 它可以用来检测文件或字符串的相似度，特别适合用于代码克隆检测
// 与传统的加密哈希(如MD5、SHA256)不同，TLSH可以度量数据的相似程度
type TLSH struct {
    buckets     [256]byte  // 256个桶用于存储三元组的分布
    checksum    [3]byte    // 3字节校验和
    lValue      byte       // 数据长度的对数值
    q1Ratio     byte       // 第一四分位数比率
    q2Ratio     byte       // 中位数比率
    qRatio      byte       // 第三四分位数比率
    windowSize  int        // 滑动窗口大小，用于处理输入数据
    slideWindow []byte     // 滑动窗口缓冲区
}

// NewTLSH 创建新的TLSH实例
// 默认使用5字节的滑动窗口大小，这是经验值
// 较大的窗口会增加精度但降低性能，较小的窗口则相反
func NewTLSH() *TLSH {
    return &TLSH{
        windowSize:  5,
        slideWindow: make([]byte, 0),
    }
}

// Update 更新哈希数据
// 使用滑动窗口方式处理输入数据
// 每次处理windowSize大小的数据块
func (t *TLSH) Update(data []byte) {
    // 将新数据追加到滑动窗口
    t.slideWindow = append(t.slideWindow, data...)
    if len(t.slideWindow) < t.windowSize {
        return
    }

    // 对每个可能的窗口位置进行处理
    for i := 0; i <= len(t.slideWindow)-t.windowSize; i++ {
        window := t.slideWindow[i : i+t.windowSize]
        t.updateBuckets(window)
    }

    // 仅保留最后的窗口数据，用于下次更新
    if len(t.slideWindow) > t.windowSize {
        t.slideWindow = t.slideWindow[len(t.slideWindow)-t.windowSize+1:]
    }
}

// updateBuckets 更新桶值
// 使用三元组映射到256个桶中
// 同时更新校验和
func (t *TLSH) updateBuckets(window []byte) {
    // 使用三个字节构造三元组值
    tripletValue := (int(window[0]) << 16) | (int(window[2]) << 8) | int(window[4])
    
    // 使用模运算将三元组映射到桶索引
    bucketIndex := tripletValue % 256
    t.buckets[bucketIndex]++

    // 使用不同的位移量更新三个校验和
    for _, b := range window {
        t.checksum[0] = t.checksum[0] + b
        t.checksum[1] = t.checksum[1] + (b << 1)
        t.checksum[2] = t.checksum[2] + (b << 2)
    }
}

// Final 完成哈希计算并返回结果
// 返回的是十六进制编码的哈希字符串
func (t *TLSH) Final() string {
    if t.isEmpty() {
        return ""
    }

    // 计算四分位数作为数据分布的特征
    quartiles := t.calculateQuartiles()
    t.q1Ratio = byte(quartiles[0])
    t.q2Ratio = byte(quartiles[1])
    t.qRatio = byte(quartiles[2])

    // 计算数据长度的对数值
    t.lValue = byte(math.Log2(float64(len(t.slideWindow))))

    // 构造最终的哈希值
    var result bytes.Buffer

    // 写入头部信息
    result.WriteByte(t.checksum[0])
    result.WriteByte(t.checksum[1])
    result.WriteByte(t.checksum[2])
    result.WriteByte(t.lValue)
    result.WriteByte(t.q1Ratio)
    result.WriteByte(t.q2Ratio)
    result.WriteByte(t.qRatio)

    // 写入桶的分布信息
    for _, b := range t.buckets {
        result.WriteByte(b)
    }

    return hex.EncodeToString(result.Bytes())
}

// calculateQuartiles 计算四分位数
// 返回三个值：第一四分位数、中位数和第三四分位数
func (t *TLSH) calculateQuartiles() []int {
    // 提取非零桶值并排序
    bucketValues := make([]int, 0, 256)
    for _, v := range t.buckets {
        if v > 0 {
            bucketValues = append(bucketValues, int(v))
        }
    }
    sort.Ints(bucketValues)

    if len(bucketValues) == 0 {
        return []int{0, 0, 0}
    }

    // 计算四分位数的位置
    q1Pos := len(bucketValues) / 4
    q2Pos := len(bucketValues) / 2
    q3Pos := (len(bucketValues) * 3) / 4

    return []int{
        bucketValues[q1Pos],
        bucketValues[q2Pos],
        bucketValues[q3Pos],
    }
}

// isEmpty 检查是否有有效数据
// 通过检查所有桶是否都为空来判断
func (t *TLSH) isEmpty() bool {
    for _, b := range t.buckets {
        if b > 0 {
            return false
        }
    }
    return true
}

// Distance 计算两个TLSH哈希的距离
// 返回值越小表示两个哈希越相似
// 返回-1表示无法比较（至少有一个哈希为空）
func (t *TLSH) Distance(other *TLSH) int {
    if t.isEmpty() || other.isEmpty() {
        return -1
    }

    distance := 0

    // 比较校验和的差异
    for i := 0; i < 3; i++ {
        distance += int(math.Abs(float64(t.checksum[i]) - float64(other.checksum[i])))
    }

    // 比较长度值的差异
    distance += int(math.Abs(float64(t.lValue) - float64(other.lValue)))

    // 比较四分位数比率的差异
    distance += int(math.Abs(float64(t.q1Ratio) - float64(other.q1Ratio)))
    distance += int(math.Abs(float64(t.q2Ratio) - float64(other.q2Ratio)))
    distance += int(math.Abs(float64(t.qRatio) - float64(other.qRatio)))

    // 比较桶值的差异
    for i := 0; i < 256; i++ {
        distance += int(math.Abs(float64(t.buckets[i]) - float64(other.buckets[i])))
    }

    return distance
}

// Reset 重置TLSH状态
// 清空所有内部状态，使对象可以重新使用
func (t *TLSH) Reset() {
    t.buckets = [256]byte{}
    t.checksum = [3]byte{}
    t.lValue = 0
    t.q1Ratio = 0
    t.q2Ratio = 0
    t.qRatio = 0
    t.slideWindow = make([]byte, 0)
}

// Hash 便捷函数，直接计算数据的TLSH哈希
// 适用于一次性计算小数据量的场景
// 对于大数据量或流式数据，建议使用Update方法
func Hash(data []byte) string {
    tlsh := NewTLSH()
    tlsh.Update(data)
    return tlsh.Final()
} 